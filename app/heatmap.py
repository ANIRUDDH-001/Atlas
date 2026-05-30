import structlog
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.db import get_db
from app.models import HeatmapResponse, HeatmapZone

router = APIRouter(tags=["analytics"])
logger = structlog.get_logger()


@router.get(
    "/{store_id}/heatmap",
    response_model=HeatmapResponse,
    summary="Zone visit frequency and dwell heatmap, normalised 0–100",
    responses={503: {"description": "Database unavailable"}},
)
async def get_heatmap(
    store_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> HeatmapResponse:
    trace_id = getattr(request.state, "trace_id", "unknown")
    now = datetime.now(timezone.utc)

    # Zone visit counts (ZONE_ENTER events)
    visit_rows = await db.execute(text("""
        SELECT zone_id, COUNT(*) AS visit_count
        FROM events
        WHERE store_id = :store_id
          AND event_type = 'ZONE_ENTER'
          AND is_staff = FALSE
          AND timestamp::date = CURRENT_DATE
          AND zone_id IS NOT NULL
        GROUP BY zone_id
    """), {"store_id": store_id})
    visit_data = {row.zone_id: row.visit_count
                  for row in visit_rows.fetchall()}

    # Zone dwell averages (ZONE_DWELL events)
    dwell_rows = await db.execute(text("""
        SELECT zone_id, AVG(dwell_ms) / 1000.0 AS avg_dwell_sec
        FROM events
        WHERE store_id = :store_id
          AND event_type = 'ZONE_DWELL'
          AND is_staff = FALSE
          AND timestamp::date = CURRENT_DATE
          AND zone_id IS NOT NULL
        GROUP BY zone_id
    """), {"store_id": store_id})
    dwell_data = {row.zone_id: float(row.avg_dwell_sec)
                  for row in dwell_rows.fetchall()}

    # Total sessions for confidence flag
    session_row = await db.execute(text("""
        SELECT COUNT(DISTINCT visitor_id) AS cnt
        FROM events
        WHERE store_id = :store_id
          AND event_type = 'ENTRY'
          AND is_staff = FALSE
          AND timestamp::date = CURRENT_DATE
    """), {"store_id": store_id})
    total_sessions = session_row.scalar() or 0
    data_confidence = "LOW" if total_sessions < 20 else "HIGH"

    # Normalisation — max visit count = 100
    all_zones = set(visit_data.keys()) | set(dwell_data.keys())
    max_visits = max(visit_data.values(), default=1)

    zones: list[HeatmapZone] = []
    for zone_id in sorted(all_zones):
        visit_count = visit_data.get(zone_id, 0)
        avg_dwell   = dwell_data.get(zone_id, 0.0)
        normalised  = round((visit_count / max_visits) * 100.0, 1)

        zones.append(HeatmapZone(
            zone_id=zone_id,
            visit_count=visit_count,
            avg_dwell_sec=round(avg_dwell, 1),
            normalised_score=normalised,
        ))

    # Sort descending by normalised_score for dashboard rendering
    zones.sort(key=lambda z: z.normalised_score, reverse=True)

    logger.info("heatmap_computed", store_id=store_id, trace_id=trace_id,
                zone_count=len(zones), confidence=data_confidence)

    return HeatmapResponse(
        store_id=store_id,
        zones=zones,
        data_confidence=data_confidence,
        as_of=now,
    )
