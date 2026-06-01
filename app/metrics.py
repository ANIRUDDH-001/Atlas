import json
import structlog
from datetime import datetime, timezone, date
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.db import get_db
from app.cache import get_redis
from app.models import MetricsResponse, ZoneDwell
from app.config import get_settings
from app.constants import POS_CORRELATION_WINDOW_SECONDS
from app.validators import validate_store_id

router = APIRouter(tags=["analytics"])
logger = structlog.get_logger()
settings = get_settings()


@router.get(
    "/{store_id}/metrics",
    response_model=MetricsResponse,
    summary="Real-time store metrics including conversion rate",
    responses={503: {"description": "Database unavailable"}},
)
async def get_metrics(
    store_id: str,
    request: Request,
    target_date: date | None = None,
    db: AsyncSession = Depends(get_db),
    cache=Depends(get_redis),
) -> MetricsResponse:
    store_id = validate_store_id(store_id)
    trace_id = getattr(request.state, "trace_id", "unknown")

    # L1 cache check
    cache_key = f"metrics:{store_id}:{target_date or 'today'}"
    try:
        cached = await cache.get(cache_key)
        if cached:
            data = json.loads(cached)
            logger.info("metrics_computed", store_id=store_id, trace_id=trace_id,
                        visitors=data.get("unique_visitors"),
                        conversion=data.get("conversion_rate"),
                        cache_hit=True)
            return MetricsResponse(**data)
    except Exception as exc:
        logger.warning("metrics_cache_read_failed", store_id=store_id, error=type(exc).__name__)

    result = await compute_metrics(store_id, target_date, db)

    # Store in cache
    try:
        await cache.setex(
            cache_key,
            settings.metrics_cache_ttl_seconds,
            result.model_dump_json(),
        )
    except Exception as exc:
        logger.warning("metrics_cache_write_failed", store_id=store_id, error=type(exc).__name__)
    logger.info("metrics_computed", store_id=store_id, trace_id=trace_id,
                visitors=result.unique_visitors,
                conversion=result.conversion_rate,
                cache_hit=False)
    return result


async def compute_metrics(
    store_id: str,
    target_date: date | None = None,
    db: AsyncSession | None = None,
) -> MetricsResponse:
    """
    Core computation function — also called by SSE stream.
    If db is None, opens its own session.
    """
    from app.db import AsyncSessionLocal

    async def _compute(session: AsyncSession) -> MetricsResponse:
        now = datetime.now(timezone.utc)

        # 1. Unique customer visitors today (ENTRY events, not staff)
        from app.session import count_unique_sessions
        unique_visitors = await count_unique_sessions(session, store_id, target_date)

        # 2. Conversion rate via 5-minute POS window join
        conversions_row = await session.execute(text("""
            SELECT COUNT(DISTINCT e.visitor_id) AS cnt
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
        """), {"store_id": store_id,
               "window": POS_CORRELATION_WINDOW_SECONDS,
               "target_date": target_date})
        converted = conversions_row.scalar() or 0
        conversion_rate = (
            round(converted / unique_visitors, 4) if unique_visitors > 0
            else None
        )

        # 3. Average dwell per zone (ZONE_DWELL events only)
        dwell_rows = await session.execute(text("""
            SELECT zone_id, AVG(dwell_ms) / 1000.0 AS avg_dwell_sec
            FROM events
            WHERE store_id = :store_id
              AND event_type = 'ZONE_DWELL'
              AND is_staff = FALSE
              AND DATE(timestamp AT TIME ZONE 'Asia/Kolkata') = COALESCE(CAST(:target_date AS DATE), '2026-05-30'::date)
            GROUP BY zone_id
            ORDER BY avg_dwell_sec DESC
        """), {"store_id": store_id, "target_date": target_date})
        dwell_by_zone = [
            ZoneDwell(zone_id=row.zone_id,
                      avg_dwell_sec=round(float(row.avg_dwell_sec), 1))
            for row in dwell_rows.fetchall()
        ]

        # 4. Current queue depth (latest BILLING_QUEUE_JOIN)
        queue_row = await session.execute(text("""
            SELECT queue_depth FROM events
            WHERE store_id = :store_id
              AND event_type = 'BILLING_QUEUE_JOIN'
              AND is_staff = FALSE
              AND queue_depth IS NOT NULL
              AND DATE(timestamp AT TIME ZONE 'Asia/Kolkata') = COALESCE(CAST(:target_date AS DATE), '2026-05-30'::date)
            ORDER BY timestamp DESC
            LIMIT 1
        """), {"store_id": store_id, "target_date": target_date})
        queue_depth = queue_row.scalar() or 0

        # 5. Abandonment rate
        abandon_row = await session.execute(text("""
            SELECT COUNT(*) AS cnt FROM events
            WHERE store_id = :store_id
              AND event_type = 'BILLING_QUEUE_ABANDON'
              AND is_staff = FALSE
              AND DATE(timestamp AT TIME ZONE 'Asia/Kolkata') = COALESCE(CAST(:target_date AS DATE), '2026-05-30'::date)
        """), {"store_id": store_id, "target_date": target_date})
        abandon_count = abandon_row.scalar() or 0
        abandonment_rate = (
            round(abandon_count / unique_visitors, 4)
            if unique_visitors > 0 else None
        )

        # 6. Data confidence flag
        data_confidence = "LOW" if unique_visitors < 5 else "HIGH"

        return MetricsResponse(
            store_id=store_id,
            unique_visitors=unique_visitors,
            conversion_rate=conversion_rate,
            avg_dwell_by_zone=dwell_by_zone,
            current_queue_depth=queue_depth,
            abandonment_rate=abandonment_rate,
            as_of=now,
            data_confidence=data_confidence,
        )

    if db is not None:
        return await _compute(db)
    else:
        async with AsyncSessionLocal() as session:
            return await _compute(session)
