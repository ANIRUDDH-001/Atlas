import json
import structlog
from datetime import datetime, timezone, timedelta
from pathlib import Path
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.db import get_db
from app.models import AnomaliesResponse, AnomalyRecord
from app.config import get_settings
from app.constants import (
    AnomalyType, AnomalySeverity, POS_CORRELATION_WINDOW_SECONDS
)
from app.validators import validate_store_id

router = APIRouter(tags=["analytics"])
logger = structlog.get_logger()
settings = get_settings()

# Suggested action strings — specific enough for non-technical managers
SUGGESTED_ACTIONS = {
    AnomalyType.BILLING_QUEUE_SPIKE: (
        "Queue exceeds threshold. Deploy an additional billing staff member "
        "immediately. Expected resolution: 8–12 minutes at current throughput."
    ),
    AnomalyType.CONVERSION_DROP: (
        "Today's conversion rate is significantly below the 7-day average. "
        "Review funnel endpoint for drop-off stage. Check billing queue "
        "abandonment rate and staff coverage."
    ),
    AnomalyType.DEAD_ZONE: (
        "No customer activity detected in this zone for 30+ minutes. "
        "Consider promotional signage refresh or staff redirection to "
        "this area."
    ),
    AnomalyType.STALE_FEED: (
        "Camera feed appears inactive. Check camera power and network "
        "connectivity. Alert on-call engineer if not resolved in 5 minutes."
    ),
}


@router.get(
    "/{store_id}/anomalies",
    response_model=AnomaliesResponse,
    summary="Active operational anomalies with severity and suggested actions",
    responses={503: {"description": "Database unavailable"}},
)
async def get_anomalies(
    store_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AnomaliesResponse:
    store_id = validate_store_id(store_id)
    trace_id = getattr(request.state, "trace_id", "unknown")
    now = datetime.now(timezone.utc)
    anomalies: list[AnomalyRecord] = []

    # ── 1. Billing Queue Spike ───────────────────────────────────────────────
    queue_row = await db.execute(text("""
        SELECT queue_depth FROM events
        WHERE store_id = :store_id
          AND event_type = 'BILLING_QUEUE_JOIN'
          AND is_staff = FALSE
          AND queue_depth IS NOT NULL
          AND timestamp >= NOW() - INTERVAL '5 minutes'
        ORDER BY timestamp DESC
        LIMIT 1
    """), {"store_id": store_id})
    current_queue = queue_row.scalar() or 0

    if current_queue > settings.queue_warn_threshold:
        severity = (
            AnomalySeverity.CRITICAL
            if current_queue > settings.queue_critical_threshold
            else AnomalySeverity.WARN
        )
        anomalies.append(AnomalyRecord(
            anomaly_id=AnomalyType.BILLING_QUEUE_SPIKE.value,
            severity=severity.value,
            value=float(current_queue),
            threshold=float(settings.queue_warn_threshold),
            suggested_action=SUGGESTED_ACTIONS[AnomalyType.BILLING_QUEUE_SPIKE],
            detected_at=now,
        ))

    # ── 2. Conversion Drop vs 7-day rolling average ──────────────────────────
    today_rate = await _compute_daily_conversion(db, store_id, days_ago=0)
    avg_rate   = await _compute_7day_avg_conversion(db, store_id)

    if today_rate is not None and avg_rate is not None and avg_rate > 0:
        if today_rate < avg_rate * settings.conversion_drop_threshold:
            drop_pct = round((avg_rate - today_rate) / avg_rate * 100, 1)
            anomalies.append(AnomalyRecord(
                anomaly_id=AnomalyType.CONVERSION_DROP.value,
                severity=AnomalySeverity.WARN.value,
                value=today_rate,
                baseline=avg_rate,
                drop_pct=drop_pct,
                suggested_action=SUGGESTED_ACTIONS[AnomalyType.CONVERSION_DROP],
                detected_at=now,
            ))

    # ── 3. Dead Zones ─────────────────────────────────────────────────────────
    all_zones = _load_store_zones(store_id)
    if all_zones:
        active_rows = await db.execute(text("""
            SELECT DISTINCT zone_id FROM events
            WHERE store_id = :store_id
              AND is_staff = FALSE
              AND zone_id IS NOT NULL
              AND timestamp >= NOW() - INTERVAL '1 minute' * :minutes
        """), {"store_id": store_id,
               "minutes": settings.dead_zone_minutes})
        active_zones = {row.zone_id for row in active_rows.fetchall()}

        for zone in all_zones:
            if zone not in active_zones:
                anomalies.append(AnomalyRecord(
                    anomaly_id=AnomalyType.DEAD_ZONE.value,
                    severity=AnomalySeverity.INFO.value,
                    zone_id=zone,
                    suggested_action=SUGGESTED_ACTIONS[AnomalyType.DEAD_ZONE],
                    detected_at=now,
                ))
    else:
        logger.warning("dead_zone_skipped",
                       store_id=store_id,
                       reason="store_layout.json not found")

    # ── 4. Stale Feed ─────────────────────────────────────────────────────────
    stale_row = await db.execute(text("""
        SELECT MAX(timestamp) AS last_event FROM events
        WHERE store_id = :store_id
    """), {"store_id": store_id})
    last_event_ts = stale_row.scalar()

    if last_event_ts is None:
        # No events ever — treat as stale
        stale = True
    else:
        if last_event_ts.tzinfo is None:
            last_event_ts = last_event_ts.replace(tzinfo=timezone.utc)
        stale = (now - last_event_ts) > timedelta(
            minutes=settings.stale_feed_minutes
        )

    if stale:
        anomalies.append(AnomalyRecord(
            anomaly_id=AnomalyType.STALE_FEED.value,
            severity=AnomalySeverity.CRITICAL.value,
            suggested_action=SUGGESTED_ACTIONS[AnomalyType.STALE_FEED],
            detected_at=now,
        ))

    logger.info("anomalies_computed", store_id=store_id,
                trace_id=trace_id, count=len(anomalies))

    return AnomaliesResponse(
        store_id=store_id,
        anomalies=anomalies,
        as_of=now,
    )


# ── Helper Functions ──────────────────────────────────────────────────────────

async def _compute_daily_conversion(
    db: AsyncSession, store_id: str, days_ago: int
) -> float | None:
    target_date = datetime.now(timezone.utc).date() - timedelta(days=days_ago)
    visitors_row = await db.execute(text("""
        SELECT COUNT(DISTINCT visitor_id) AS cnt
        FROM events
        WHERE store_id = :store_id AND is_staff = FALSE
          AND event_type = 'ENTRY' AND timestamp::date = :target_date
    """), {"store_id": store_id, "target_date": target_date})
    visitors = visitors_row.scalar() or 0
    if visitors == 0:
        return None

    converted_row = await db.execute(text("""
        SELECT COUNT(DISTINCT e.visitor_id) AS cnt
        FROM events e
        JOIN pos_transactions p
          ON e.store_id = p.store_id
         AND e.timestamp BETWEEN
             p.timestamp - INTERVAL '1 second' * :window
             AND p.timestamp
        WHERE e.store_id = :store_id
          AND e.zone_id IN ('BILLING','CHECKOUT','CASH_COUNTER')
          AND e.is_staff = FALSE
          AND e.timestamp::date = :target_date
    """), {"store_id": store_id,
           "target_date": target_date,
           "window": POS_CORRELATION_WINDOW_SECONDS})
    converted = converted_row.scalar() or 0
    return round(converted / visitors, 4)


async def _compute_7day_avg_conversion(
    db: AsyncSession, store_id: str
) -> float | None:
    rates = []
    for days_ago in range(1, 8):
        rate = await _compute_daily_conversion(db, store_id, days_ago)
        if rate is not None:
            rates.append(rate)
    if not rates:
        return None
    return round(sum(rates) / len(rates), 4)


def _load_store_zones(store_id: str) -> list[str]:
    """Load zone names from store_layout.json for dead zone detection."""
    layout_path = Path(settings.store_layout_path)
    if not layout_path.exists():
        return []
    try:
        layout = json.loads(layout_path.read_text())
        store = layout.get(store_id, {})
        return list(store.get("zones", {}).keys())
    except Exception:
        return []
