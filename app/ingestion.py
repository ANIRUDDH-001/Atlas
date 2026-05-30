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

    # Batch size guard (Pydantic enforces max_length=500 but belt-and-suspenders)
    if len(payload.events) > MAX_INGEST_BATCH_SIZE:
        from fastapi.responses import JSONResponse
        return JSONResponse(
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

    for event in payload.events:
        validate_store_id(event.store_id)
        try:
            await _insert_event(db, event)
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
                reason=str(exc),
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
        total=len(payload.events),
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
    await db.execute(
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
