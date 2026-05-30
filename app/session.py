"""
Session Management — canonical session definition and shared query helpers.

A "session" is defined as a unique visitor_id for a given store_id on a
given calendar date. Re-entry events (event_type=REENTRY) do NOT create a
new session — they associate back to the same visitor_id. A visitor's
session begins at their first ENTRY event and continues until their last
EXIT or REENTRY event for that day. Staff events (is_staff=TRUE) are
NEVER included in session counts.
"""
import structlog
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = structlog.get_logger()


async def count_unique_sessions(
    db: AsyncSession,
    store_id: str,
    target_date: date | None = None,
) -> int:
    """
    Count unique customer sessions for a store on a given date.
    Uses ENTRY events as session anchors.
    REENTRY does not add to this count.
    Staff excluded.
    """
    params: dict = {"store_id": store_id}
    if target_date:
        params["target_date"] = target_date
        query = text("""
            SELECT COUNT(DISTINCT visitor_id) AS cnt
            FROM events
            WHERE store_id = :store_id
              AND is_staff = FALSE
              AND event_type = 'ENTRY'
              AND timestamp::date = :target_date
        """)
    else:
        query = text("""
            SELECT COUNT(DISTINCT visitor_id) AS cnt
            FROM events
            WHERE store_id = :store_id
              AND is_staff = FALSE
              AND event_type = 'ENTRY'
              AND timestamp::date = CURRENT_DATE
        """)

    row = await db.execute(query, params)
    return row.scalar() or 0


async def get_session_summary(
    db: AsyncSession,
    store_id: str,
) -> list[dict]:
    """
    Returns a per-visitor session summary for today.
    Used by funnel and anomaly logic.
    Each row: visitor_id, entered, visited_zone, reached_billing, reentry_count
    """
    rows = await db.execute(text("""
        SELECT
            visitor_id,
            BOOL_OR(event_type = 'ENTRY')                              AS entered,
            BOOL_OR(event_type IN ('ZONE_ENTER','ZONE_DWELL')
                    AND zone_id IS NOT NULL)                            AS visited_zone,
            BOOL_OR(event_type = 'BILLING_QUEUE_JOIN')                 AS reached_billing,
            COUNT(*) FILTER (WHERE event_type = 'REENTRY')             AS reentry_count,
            MIN(timestamp)                                             AS first_seen,
            MAX(timestamp)                                             AS last_seen
        FROM events
        WHERE store_id = :store_id
          AND is_staff = FALSE
          AND timestamp::date = CURRENT_DATE
        GROUP BY visitor_id
    """), {"store_id": store_id})
    return [dict(row._mapping) for row in rows.fetchall()]


async def get_visitor_zone_presence(
    db: AsyncSession,
    store_id: str,
    visitor_id: str,
    zone_id: str,
    window_seconds: int,
    reference_timestamp,
) -> bool:
    """
    Check if a visitor was present in a specific zone within
    `window_seconds` seconds before `reference_timestamp`.
    Used for POS correlation validation.
    """
    row = await db.execute(text("""
        SELECT COUNT(*) AS cnt
        FROM events
        WHERE store_id = :store_id
          AND visitor_id = :visitor_id
          AND zone_id = :zone_id
          AND is_staff = FALSE
          AND timestamp BETWEEN
              :reference_ts - INTERVAL '1 second' * :window
              AND :reference_ts
    """), {
        "store_id": store_id,
        "visitor_id": visitor_id,
        "zone_id": zone_id,
        "reference_ts": reference_timestamp,
        "window": window_seconds,
    })
    return (row.scalar() or 0) > 0


async def detect_reentry_inflation(
    db: AsyncSession,
    store_id: str,
) -> dict:
    """
    Report visitors whose reentry_count > 0.
    Useful for validating pipeline Re-ID quality.
    Returns: {total_visitors, reentry_visitors, reentry_rate}
    """
    rows = await db.execute(text("""
        SELECT
            COUNT(DISTINCT visitor_id)                              AS total,
            COUNT(DISTINCT visitor_id) FILTER (
                WHERE event_type = 'REENTRY'
            )                                                       AS reentry
        FROM events
        WHERE store_id = :store_id
          AND is_staff = FALSE
          AND timestamp::date = CURRENT_DATE
    """), {"store_id": store_id})
    row = rows.fetchone()
    total   = row.total   or 0
    reentry = row.reentry or 0
    return {
        "total_visitors":   total,
        "reentry_visitors": reentry,
        "reentry_rate":     round(reentry / total, 4) if total > 0 else 0.0,
    }
