import asyncio
import structlog
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Request
from sqlalchemy import text

from app.db import AsyncSessionLocal
from app.cache import get_redis
from app.models import HealthResponse, StoreHealth
from app.config import get_settings

router = APIRouter(tags=["health"])
logger = structlog.get_logger()
settings = get_settings()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service health: database, cache, and per-store feed status",
)
async def health_check(request: Request) -> HealthResponse:
    trace_id = getattr(request.state, "trace_id", "unknown")
    now = datetime.now(timezone.utc)

    # ── Check database ────────────────────────────────────────────────────────
    db_status = "OK"
    store_healths: list[StoreHealth] = []

    try:
        async with asyncio.timeout(2.0):
            async with AsyncSessionLocal() as session:
                await session.execute(text("SELECT 1"))

                # Per-store feed status
                store_rows = await session.execute(text("""
                    SELECT
                        store_id,
                        MAX(timestamp)  AS last_event,
                        COUNT(*)        AS event_count_today
                    FROM events
                    WHERE DATE(timestamp) = CURRENT_DATE
                    GROUP BY store_id
                    ORDER BY store_id
                """))
                for row in store_rows.fetchall():
                    last_ts = row.last_event
                    if last_ts is not None and last_ts.tzinfo is None:
                        last_ts = last_ts.replace(tzinfo=timezone.utc)

                    if last_ts is None:
                        feed_status = "NO_DATA"
                    elif (now - last_ts) > timedelta(
                        minutes=settings.stale_feed_minutes
                    ):
                        feed_status = "STALE"
                    else:
                        feed_status = "LIVE"

                    store_healths.append(StoreHealth(
                        store_id=row.store_id,
                        last_event_timestamp=last_ts,
                        feed_status=feed_status,
                        event_count_today=row.event_count_today,
                    ))

    except (asyncio.TimeoutError, Exception) as exc:
        db_status = "UNAVAILABLE"
        logger.error("health_db_unavailable", error=type(exc).__name__)

    # ── Check Redis ───────────────────────────────────────────────────────────
    cache_status = "OK"
    try:
        async with asyncio.timeout(1.0):
            redis = await get_redis()
            await redis.ping()
    except Exception as exc:
        cache_status = "UNAVAILABLE"
        logger.error("health_cache_unavailable", error=type(exc).__name__)

    # ── Overall status ────────────────────────────────────────────────────────
    if db_status == "UNAVAILABLE" and cache_status == "UNAVAILABLE":
        overall = "DOWN"
    elif db_status == "UNAVAILABLE" or cache_status == "UNAVAILABLE":
        overall = "DEGRADED"
    elif any(s.feed_status == "STALE" for s in store_healths):
        overall = "DEGRADED"
    else:
        overall = "OK"

    logger.info("health_check", trace_id=trace_id, status=overall,
                db=db_status, cache=cache_status,
                store_count=len(store_healths))

    return HealthResponse(
        status=overall,
        database=db_status,
        cache=cache_status,
        stores=store_healths,
        checked_at=now,
    )
