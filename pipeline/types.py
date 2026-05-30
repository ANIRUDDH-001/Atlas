"""Shared types for pipeline inter-module communication."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import numpy as np


@dataclass
class Detection:
    """Raw YOLO detection for a single person in a frame."""
    track_id: int
    bbox: tuple[float, float, float, float]  # x1, y1, x2, y2
    confidence: float
    frame_idx: int
    timestamp: datetime
    camera_id: str
    frame_crop: object = None  # Added for staff detection


@dataclass
class TrackedVisitor:
    """A detection enriched with Re-ID and zone information."""
    detection: Detection
    visitor_id: str
    event_type: str        # From EventType enum values
    zone_id: Optional[str]
    is_staff: bool
    embedding: Optional[np.ndarray]
    session_seq: int


@dataclass
class ZoneDefinition:
    """A named zone with polygon coordinates for one camera view."""
    zone_id: str
    camera_id: str
    polygon: list[tuple[float, float]]  # [(x,y), ...] normalised 0.0–1.0


@dataclass
class StoreLayout:
    """Parsed store_layout.json for one store."""
    store_id: str
    cameras: dict[str, dict]   # camera_id → {threshold_y, ...}
    zones: dict[str, list[ZoneDefinition]]  # zone_id → [ZoneDef per camera]
    open_hours: dict           # {open: "09:00", close: "21:00"}
