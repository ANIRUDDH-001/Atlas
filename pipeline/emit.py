"""
Event Emitter — constructs StoreEvent dicts and writes to JSONL.

Manages:
- Zone dwell timer state (ZONE_DWELL every 30s)
- Billing queue depth tracking (BILLING_QUEUE_JOIN queue_depth field)
- BILLING_QUEUE_ABANDON detection (exit billing without purchase)
- Output file buffering (write + flush per batch)
"""
import json
import uuid
import structlog
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from typing import Optional

from pipeline.types import TrackedVisitor
from pipeline.config import PipelineConfig
from app.constants import EventType, BILLING_ZONES

logger = structlog.get_logger()


@dataclass
class DwellState:
    """Tracks continuous dwell for one visitor in one zone."""
    zone_id: str
    entered_at: datetime
    last_dwell_emitted_at: Optional[datetime] = None


@dataclass
class BillingState:
    """Tracks billing queue membership for one visitor."""
    visitor_id: str
    entered_at: datetime
    queue_depth_at_join: int


class EventEmitter:
    """
    Stateful event emitter for the detection pipeline.

    Constructs complete StoreEvent dicts from TrackedVisitor objects
    and writes them to a JSONL output file.
    """

    def __init__(self, output_path: Path, config: PipelineConfig):
        self._path = output_path
        self._config = config
        self._file = open(str(output_path), "a", encoding="utf-8", buffering=1)

        # Per-visitor state
        self._dwell_states: dict[str, DwellState] = {}     # visitor_id → dwell
        self._billing_states: dict[str, BillingState] = {} # visitor_id → billing
        self._visitor_zones: dict[str, Optional[str]] = {} # visitor_id → current zone
        self._zone_populations: dict[str, set[str]] = {}   # zone_id → {visitor_ids}

        self._event_count = 0
        logger.info("emitter_initialized", output=str(output_path))

    def emit(
        self,
        visitor: TrackedVisitor,
        store_id: str,
        frame_shape: tuple,
    ) -> Optional[dict]:
        """
        Process a TrackedVisitor and emit appropriate events to JSONL.

        May emit 0, 1, or 2 events per call (e.g., ZONE_EXIT + ZONE_ENTER
        when a visitor transitions between zones, plus a ZONE_DWELL if
        30s has elapsed in the previous zone).

        Returns the last emitted event dict, or None if nothing emitted.
        """
        visitor_id  = visitor.visitor_id
        event_type  = visitor.event_type
        zone_id     = visitor.zone_id
        timestamp   = visitor.detection.timestamp
        last_event  = None

        # ── Handle ENTRY / REENTRY ────────────────────────────────────────────
        if event_type in (EventType.ENTRY.value, EventType.REENTRY.value):
            last_event = self._write_event(
                store_id=store_id,
                visitor=visitor,
                event_type=event_type,
                zone_id=None,  # Must be null for ENTRY/REENTRY
                dwell_ms=0,
            )
            self._visitor_zones[visitor_id] = None
            return last_event

        # ── Handle EXIT ───────────────────────────────────────────────────────
        if event_type == EventType.EXIT.value:
            # Check if visitor was in billing — emit BILLING_QUEUE_ABANDON
            if visitor_id in self._billing_states:
                last_event = self._write_event(
                    store_id=store_id,
                    visitor=visitor,
                    event_type=EventType.BILLING_QUEUE_ABANDON.value,
                    zone_id=list(BILLING_ZONES)[0],
                    dwell_ms=0,
                )
                del self._billing_states[visitor_id]

            last_event = self._write_event(
                store_id=store_id,
                visitor=visitor,
                event_type=EventType.EXIT.value,
                zone_id=None,
                dwell_ms=0,
            )
            # Clear all state for this visitor
            self._visitor_zones.pop(visitor_id, None)
            self._dwell_states.pop(visitor_id, None)
            self._remove_from_all_zones(visitor_id)
            return last_event

        # ── Handle zone transitions ───────────────────────────────────────────
        current_zone = self._visitor_zones.get(visitor_id)

        if zone_id != current_zone:
            # Zone exit
            if current_zone is not None:
                dwell_ms = self._compute_dwell_ms(visitor_id, timestamp)
                self._write_event(
                    store_id=store_id,
                    visitor=visitor,
                    event_type=EventType.ZONE_EXIT.value,
                    zone_id=current_zone,
                    dwell_ms=dwell_ms,
                )
                self._remove_from_zone(visitor_id, current_zone)
                # Clear billing state if leaving billing zone entirely without purchase
                if current_zone in BILLING_ZONES and visitor_id in self._billing_states:
                    # If the new zone is NOT a billing zone, it's an abandon.
                    if zone_id not in BILLING_ZONES:
                        self._write_event(
                            store_id=store_id,
                            visitor=visitor,
                            event_type=EventType.BILLING_QUEUE_ABANDON.value,
                            zone_id=current_zone,
                            dwell_ms=dwell_ms,
                        )
                        del self._billing_states[visitor_id]

            # Zone enter
            if zone_id is not None:
                self._add_to_zone(visitor_id, zone_id)
                queue_depth = self._get_queue_depth(zone_id)

                enter_event_type = EventType.ZONE_ENTER.value
                # Check if this is a billing queue join
                if zone_id in BILLING_ZONES and queue_depth > 0:
                    enter_event_type = EventType.BILLING_QUEUE_JOIN.value
                    self._billing_states[visitor_id] = BillingState(
                        visitor_id=visitor_id,
                        entered_at=timestamp,
                        queue_depth_at_join=queue_depth,
                    )

                last_event = self._write_event(
                    store_id=store_id,
                    visitor=visitor,
                    event_type=enter_event_type,
                    zone_id=zone_id,
                    dwell_ms=0,
                    queue_depth=queue_depth if enter_event_type == EventType.BILLING_QUEUE_JOIN.value else None,
                )
                self._dwell_states[visitor_id] = DwellState(
                    zone_id=zone_id,
                    entered_at=timestamp,
                )

            self._visitor_zones[visitor_id] = zone_id

        else:
            # Same zone — check if ZONE_DWELL should be emitted
            if zone_id is not None and visitor_id in self._dwell_states:
                dwell_state = self._dwell_states[visitor_id]
                elapsed = (timestamp - dwell_state.entered_at).total_seconds()
                last_emit = dwell_state.last_dwell_emitted_at or dwell_state.entered_at
                since_last = (timestamp - last_emit).total_seconds()

                if since_last >= self._config.dwell_emit_interval_sec:
                    last_event = self._write_event(
                        store_id=store_id,
                        visitor=visitor,
                        event_type=EventType.ZONE_DWELL.value,
                        zone_id=zone_id,
                        dwell_ms=int(elapsed * 1000),
                    )
                    dwell_state.last_dwell_emitted_at = timestamp

        return last_event

    def flush(self) -> None:
        """Flush buffered writes to disk."""
        self._file.flush()

    def close(self) -> None:
        """Close the output file."""
        self._file.flush()
        self._file.close()
        logger.info("emitter_closed",
                    output=str(self._path),
                    total_events=self._event_count)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _write_event(
        self,
        store_id: str,
        visitor: TrackedVisitor,
        event_type: str,
        zone_id: Optional[str],
        dwell_ms: int,
        queue_depth: Optional[int] = None,
    ) -> dict:
        """Construct and write one event to JSONL."""
        event = {
            "event_id":   str(uuid.uuid4()),
            "store_id":   store_id,
            "camera_id":  visitor.detection.camera_id,
            "visitor_id": visitor.visitor_id,
            "event_type": event_type,
            "timestamp":  visitor.detection.timestamp.strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "zone_id":    zone_id,
            "dwell_ms":   dwell_ms,
            "is_staff":   visitor.is_staff,
            "confidence": round(visitor.detection.confidence, 4),
            "metadata": {
                "queue_depth": queue_depth,
                "sku_zone":    zone_id,
                "session_seq": visitor.session_seq,
            },
        }
        self._file.write(json.dumps(event) + "\n")
        self._event_count += 1
        return event

    def _compute_dwell_ms(self, visitor_id: str, now: datetime) -> int:
        state = self._dwell_states.get(visitor_id)
        if state is None:
            return 0
        return int((now - state.entered_at).total_seconds() * 1000)

    def _add_to_zone(self, visitor_id: str, zone_id: str) -> None:
        if zone_id not in self._zone_populations:
            self._zone_populations[zone_id] = set()
        self._zone_populations[zone_id].add(visitor_id)

    def _remove_from_zone(self, visitor_id: str, zone_id: str) -> None:
        if zone_id in self._zone_populations:
            self._zone_populations[zone_id].discard(visitor_id)

    def _remove_from_all_zones(self, visitor_id: str) -> None:
        for zone_visitors in self._zone_populations.values():
            zone_visitors.discard(visitor_id)

    def _get_queue_depth(self, zone_id: str) -> int:
        """Current number of visitors in a zone (before this new visitor)."""
        return len(self._zone_populations.get(zone_id, set()))
