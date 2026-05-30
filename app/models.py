from pydantic import BaseModel, Field, field_validator, UUID4
from typing import Optional
from datetime import datetime
from app.constants import EventType

class EventMetadata(BaseModel):
    queue_depth: Optional[int] = Field(None, ge=0)
    sku_zone: Optional[str] = None
    session_seq: int = Field(..., ge=1)

class StoreEvent(BaseModel):
    event_id: str = Field(..., description="UUID v4 string")
    store_id: str = Field(..., min_length=1, max_length=64)
    camera_id: str = Field(..., min_length=1, max_length=64)
    visitor_id: str = Field(..., min_length=1, max_length=64)
    event_type: EventType
    timestamp: datetime
    zone_id: Optional[str] = None
    dwell_ms: int = Field(default=0, ge=0)
    is_staff: bool = False
    confidence: float = Field(..., ge=0.0, le=1.0)
    metadata: EventMetadata

    @field_validator("event_id")
    @classmethod
    def validate_uuid(cls, v: str) -> str:
        import uuid
        try:
            uuid.UUID(v, version=4)
        except ValueError:
            raise ValueError(f"event_id must be a valid UUID v4, got: {v}")
        return v

    @field_validator("timestamp", mode="before")
    @classmethod
    def parse_timestamp(cls, v):
        if isinstance(v, str):
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        return v

    @field_validator("zone_id")
    @classmethod
    def validate_zone_for_entry_exit(cls, v, info):
        event_type = info.data.get("event_type")
        if event_type in (EventType.ENTRY, EventType.EXIT, EventType.REENTRY):
            if v is not None:
                raise ValueError(
                    f"zone_id must be null for event_type={event_type}"
                )
        elif event_type in (
            EventType.ZONE_ENTER, EventType.ZONE_EXIT,
            EventType.ZONE_DWELL, EventType.BILLING_QUEUE_JOIN,
            EventType.BILLING_QUEUE_ABANDON
        ):
            if v is None:
                raise ValueError(
                    f"zone_id is required for event_type={event_type}"
                )
        return v

    @field_validator("dwell_ms")
    @classmethod
    def validate_dwell_ms(cls, v, info):
        event_type = info.data.get("event_type")
        if event_type == EventType.ZONE_DWELL and v < 30000:
            raise ValueError(
                "ZONE_DWELL events must have dwell_ms >= 30000"
            )
        return v

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}

class EventBatch(BaseModel):
    events: list[StoreEvent] = Field(..., min_length=1, max_length=500)

# ── Ingest Response ─────────────────────────────────────────────────────────
class IngestError(BaseModel):
    event_id: str
    reason: str

class IngestResponse(BaseModel):
    accepted: int
    rejected: int
    errors: list[IngestError] = []

# ── Metrics Response ─────────────────────────────────────────────────────────
class ZoneDwell(BaseModel):
    zone_id: str
    avg_dwell_sec: float

class MetricsResponse(BaseModel):
    store_id: str
    unique_visitors: int
    conversion_rate: Optional[float] = None  # null if zero visitors
    avg_dwell_by_zone: list[ZoneDwell] = []
    current_queue_depth: int = 0
    abandonment_rate: Optional[float] = None
    as_of: datetime
    data_confidence: str = "HIGH"  # LOW if < 20 sessions

# ── Funnel Response ───────────────────────────────────────────────────────────
class FunnelStage(BaseModel):
    stage: str
    count: int
    dropoff_pct: float

class FunnelResponse(BaseModel):
    store_id: str
    funnel: list[FunnelStage]
    as_of: datetime

# ── Heatmap Response ──────────────────────────────────────────────────────────
class HeatmapZone(BaseModel):
    zone_id: str
    visit_count: int
    avg_dwell_sec: float
    normalised_score: float = Field(..., ge=0.0, le=100.0)

class HeatmapResponse(BaseModel):
    store_id: str
    zones: list[HeatmapZone]
    data_confidence: str  # LOW if < 20 sessions
    as_of: datetime

# ── Anomaly Response ──────────────────────────────────────────────────────────
class AnomalyRecord(BaseModel):
    anomaly_id: str
    severity: str  # INFO / WARN / CRITICAL
    value: Optional[float] = None
    threshold: Optional[float] = None
    zone_id: Optional[str] = None
    baseline: Optional[float] = None
    drop_pct: Optional[float] = None
    suggested_action: str
    detected_at: datetime

class AnomaliesResponse(BaseModel):
    store_id: str
    anomalies: list[AnomalyRecord]
    as_of: datetime

# ── Health Response ───────────────────────────────────────────────────────────
class StoreHealth(BaseModel):
    store_id: str
    last_event_timestamp: Optional[datetime] = None
    feed_status: str  # LIVE / STALE / NO_DATA
    event_count_today: int

class HealthResponse(BaseModel):
    status: str  # OK / DEGRADED / DOWN
    database: str  # OK / UNAVAILABLE
    cache: str     # OK / UNAVAILABLE
    stores: list[StoreHealth]
    checked_at: datetime
