import structlog
from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.db import get_db
from app.cache import get_redis
from app.models import EventBatch, StoreEvent, IngestResponse, IngestError
from app.constants import MAX_INGEST_BATCH_SIZE
from app.validators import validate_store_id

router = APIRouter(tags=["events"])
logger = structlog.get_logger()

# Rate limiting: 100 ingest requests per minute per source IP
RATE_LIMIT_REQUESTS = 100
RATE_LIMIT_WINDOW   = 60   # seconds

async def _check_rate_limit(request: Request, cache) -> bool:
    """
    Returns True if request is within rate limit, False if exceeded.
    Uses Redis INCR + EXPIRE sliding window.
    """
    client_ip = request.client.host if request.client else "unknown"
    key = f"ratelimit:ingest:{client_ip}"
    try:
        count = await cache.incr(key)
        if count == 1:
            await cache.expire(key, RATE_LIMIT_WINDOW)
        return count <= RATE_LIMIT_REQUESTS
    except Exception:
        return True  # Redis down → allow request (fail open)


@router.post(
    "/events/ingest",
    response_model=IngestResponse,
    summary="Ingest a batch of store events",
    responses={
        400: {"description": "Batch exceeds maximum size"},
        503: {"description": "Database unavailable"},
    },
)
async def ingest_events(
    payload: EventBatch,
    request: Request,
    db: AsyncSession = Depends(get_db),
    cache=Depends(get_redis),
) -> IngestResponse:
    trace_id = getattr(request.state, "trace_id", "unknown")

    if not await _check_rate_limit(request, cache):
        from fastapi.responses import JSONResponse
        return JSONResponse(  # type: ignore
            status_code=429,
            content={
                "error": "rate_limit_exceeded",
                "limit": RATE_LIMIT_REQUESTS,
                "window_seconds": RATE_LIMIT_WINDOW,
            },
            headers={"Retry-After": str(RATE_LIMIT_WINDOW)},
        )

    # Batch size guard (Pydantic enforces max_length=500 but belt-and-suspenders)
    if len(payload.events) > MAX_INGEST_BATCH_SIZE:
        from fastapi.responses import JSONResponse
        return JSONResponse(  # type: ignore
            status_code=400,
            content={
                "error": "batch_too_large",
                "max": MAX_INGEST_BATCH_SIZE,
                "received": len(payload.events),
            },
        )

    accepted_ids: list[str] = []
    rejected: list[IngestError] = []
    affected_stores: set[str] = set()

    for item in payload.events:
        if isinstance(item, dict):
            try:
                event = StoreEvent.model_validate(item)
            except ValidationError:
                rejected.append(IngestError(
                    event_id=item.get("event_id", "unknown"),
                    reason="malformed_event",
                ))
                continue
        else:
            event = item

        try:
            validate_store_id(event.store_id)
        except Exception:
            rejected.append(IngestError(
                event_id=event.event_id,
                reason="invalid_store",
            ))
            continue

        try:
            result = await _insert_event(db, event)  # type: ignore
            if result.rowcount != 0:  # type: ignore
                accepted_ids.append(event.event_id)
                affected_stores.add(event.store_id)
        except Exception as exc:
            logger.warning(
                "event_insert_failed",
                trace_id=trace_id,
                event_id=event.event_id,
                error=str(exc),
            )
            rejected.append(IngestError(
                event_id=event.event_id,
                reason="internal_error",
            ))

    # Commit all accepted events in one transaction
    await db.commit()

    # Invalidate Redis metric cache for all affected stores
    for store_id in affected_stores:
        try:
            await cache.delete(f"metrics:{store_id}")
        except Exception as cache_exc:
            # Cache invalidation failure is non-fatal
            logger.warning("cache_invalidation_failed",
                           store_id=store_id, error=str(cache_exc))

    logger.info(
        "ingest_complete",
        trace_id=trace_id,
        event_count=len(payload.events),
        accepted=len(accepted_ids),
        rejected=len(rejected),
        stores=list(affected_stores),
    )

    return IngestResponse(
        accepted=len(accepted_ids),
        rejected=len(rejected),
        errors=rejected,
    )


async def _insert_event(db: AsyncSession, event: StoreEvent) -> None:
    """
    Insert a single event idempotently.
    ON CONFLICT (event_id) DO NOTHING ensures safe replay.
    """
    return await db.execute(  # type: ignore
        text("""
            INSERT INTO events (
                event_id, store_id, camera_id, visitor_id,
                event_type, timestamp, zone_id, dwell_ms,
                is_staff, confidence, queue_depth, sku_zone, session_seq
            ) VALUES (
                :event_id, :store_id, :camera_id, :visitor_id,
                :event_type, :timestamp, :zone_id, :dwell_ms,
                :is_staff, :confidence, :queue_depth, :sku_zone, :session_seq
            )
            ON CONFLICT (event_id) DO NOTHING
        """),
        {
            "event_id":    event.event_id,
            "store_id":    event.store_id,
            "camera_id":   event.camera_id,
            "visitor_id":  event.visitor_id,
            "event_type":  event.event_type.value,
            "timestamp":   event.timestamp,
            "zone_id":     event.zone_id,
            "dwell_ms":    event.dwell_ms,
            "is_staff":    event.is_staff,
            "confidence":  event.confidence,
            "queue_depth": event.metadata.queue_depth,
            "sku_zone":    event.metadata.sku_zone,
            "session_seq": event.metadata.session_seq,
        },
    )
