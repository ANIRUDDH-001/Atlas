import structlog
from datetime import datetime, timezone, date
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.db import get_db
from app.models import FunnelResponse, FunnelStage
from app.constants import POS_CORRELATION_WINDOW_SECONDS
from app.validators import validate_store_id

router = APIRouter(tags=["analytics"])
logger = structlog.get_logger()


@router.get(
    "/{store_id}/funnel",
    response_model=FunnelResponse,
    summary="Conversion funnel: Entry → Zone → Billing → Purchase",
    responses={503: {"description": "Database unavailable"}},
)
async def get_funnel(
    store_id: str,
    request: Request,
    target_date: date | None = None,
    db: AsyncSession = Depends(get_db),
) -> FunnelResponse:
    store_id = validate_store_id(store_id)
    trace_id = getattr(request.state, "trace_id", "unknown")
    now = datetime.now(timezone.utc)

    # Single CTE query — each stage builds on session-level aggregation
    result = await db.execute(text("""
        WITH sessions AS (
            -- One row per unique visitor (session unit)
            SELECT
                visitor_id,
                BOOL_OR(event_type = 'ENTRY')                   AS entered,
                BOOL_OR(event_type IN ('ZONE_ENTER','ZONE_DWELL')
                        AND zone_id IS NOT NULL)                 AS visited_zone,
                BOOL_OR(event_type = 'BILLING_QUEUE_JOIN')      AS reached_billing
            FROM events
            WHERE store_id = :store_id
              AND is_staff = FALSE
              AND DATE(timestamp AT TIME ZONE 'Asia/Kolkata') = COALESCE(CAST(:target_date AS DATE), '2026-05-30'::date)
            GROUP BY visitor_id
        ),
        purchasers AS (
            -- Visitors present in billing zone within 5 min before a POS tx
            SELECT DISTINCT e.visitor_id
            FROM events e
            JOIN pos_transactions p
              ON e.store_id = p.store_id
             AND e.timestamp BETWEEN
                 p.timestamp - INTERVAL '1 second' * :window
                 AND p.timestamp
            WHERE e.store_id = :store_id
              AND e.zone_id IN ('BILLING', 'CHECKOUT', 'CASH_COUNTER')
              AND e.is_staff = FALSE
              AND DATE(e.timestamp AT TIME ZONE 'Asia/Kolkata') = COALESCE(CAST(:target_date AS DATE), '2026-05-30'::date)
        )
        SELECT
            COUNT(*) FILTER (WHERE s.entered)            AS entry_count,
            COUNT(*) FILTER (WHERE s.visited_zone)       AS zone_count,
            COUNT(*) FILTER (WHERE s.reached_billing)    AS billing_count,
            COUNT(p.visitor_id)                          AS purchase_count
        FROM sessions s
        LEFT JOIN purchasers p ON s.visitor_id = p.visitor_id
    """), {
        "store_id": store_id,
        "window": POS_CORRELATION_WINDOW_SECONDS,
        "target_date": target_date,
    })

    row = result.fetchone()
    entry    = row.entry_count    or 0  # type: ignore
    zone     = row.zone_count     or 0  # type: ignore
    billing  = row.billing_count  or 0  # type: ignore
    purchase = row.purchase_count or 0  # type: ignore

    def dropoff(stage_a: int, stage_b: int) -> float:
        if stage_a == 0:
            return 0.0
        return round((stage_a - stage_b) / stage_a * 100, 1)

    funnel_stages = [
        FunnelStage(stage="Entry",         count=entry,    dropoff_pct=0.0),
        FunnelStage(stage="Zone Visit",    count=zone,     dropoff_pct=dropoff(entry, zone)),
        FunnelStage(stage="Billing Queue", count=billing,  dropoff_pct=dropoff(zone, billing)),
        FunnelStage(stage="Purchase",      count=purchase, dropoff_pct=dropoff(billing, purchase)),
    ]

    logger.info("funnel_computed", store_id=store_id, trace_id=trace_id,
                entry=entry, purchase=purchase)

    return FunnelResponse(
        store_id=store_id,
        funnel=funnel_stages,
        as_of=now,
    )
