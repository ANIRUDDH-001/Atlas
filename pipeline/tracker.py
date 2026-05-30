"""
Visitor Gallery — persistent identity across frames and re-entries.

The gallery maintains a rolling 30-minute window of appearance embeddings.
On each new detection, the gallery:
  1. Checks if the track_id is already known → return existing visitor_id
  2. If new track: compare embedding against exited visitors in gallery
  3. If similarity > threshold → REENTRY (same visitor returning)
  4. If no match → ENTRY (new visitor)

Re-entry inflation problem: without this, a visitor who steps outside
briefly and returns would be counted as two unique visitors, inflating
unique_visitors and deflating conversion_rate.
"""
import uuid
import time
import structlog
import numpy as np
from dataclasses import dataclass, field
from typing import Optional

from pipeline.types import Detection, TrackedVisitor
from pipeline.reid import ReIDExtractor, cosine_similarity
from pipeline.config import PipelineConfig
from app.constants import EventType

logger = structlog.get_logger()


@dataclass
class GalleryEntry:
    """One visitor's record in the gallery."""
    visitor_id: str
    embedding: Optional[np.ndarray]      # L2-normalised OSNet embedding
    last_seen_ts: float                  # Unix timestamp
    exit_time: Optional[float] = None    # Set when EXIT event emitted
    session_seq: int = 0                 # Running event counter for this visitor


class VisitorGallery:
    """
    Maintains rolling appearance embeddings for re-entry detection.

    Key design decisions (documented in CHOICES.md):
    - Similarity threshold 0.72 (not AI-suggested 0.80) — retail face blur
      means embeddings rely on clothing; lower threshold reduces false negatives
    - 30-minute window — matches typical retail visit + shopping trip duration
    - Only exited visitors are candidates for re-entry matching (not current visitors)
    """

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.reid = ReIDExtractor()
        self._gallery: dict[str, GalleryEntry] = {}         # visitor_id → entry
        self._track_to_visitor: dict[int, str] = {}          # track_id → visitor_id
        self._reentry_count: int = 0
        self._entry_count: int = 0

    # ── Public API ────────────────────────────────────────────────────────────

    def resolve(
        self,
        detection: Detection,
        frame_crop: Optional[np.ndarray],
    ) -> TrackedVisitor:
        """
        Resolve a detection to a visitor identity.

        Returns TrackedVisitor with:
        - visitor_id: existing (re-entry) or new UUID-based ID
        - event_type: ENTRY (first visit) or REENTRY (returning visitor)
        - session_seq: 1-based event sequence number for this visitor
        """
        now = time.time()

        # Case 1: Already-known track ID
        if detection.track_id in self._track_to_visitor:
            visitor_id = self._track_to_visitor[detection.track_id]
            entry = self._gallery[visitor_id]
            entry.last_seen_ts = now
            entry.session_seq += 1
            return TrackedVisitor(
                detection=detection,
                visitor_id=visitor_id,
                event_type=EventType.ZONE_DWELL.value,  # Mid-session event
                zone_id=None,   # Populated by ZoneMapper downstream
                is_staff=False, # Populated by StaffDetector downstream
                embedding=entry.embedding,
                session_seq=entry.session_seq,
            )

        # Case 2: New track — extract embedding
        embedding = None
        if frame_crop is not None:
            embedding = self.reid.extract(frame_crop)

        # Case 3: Compare against exited visitors for re-entry
        matched_id, best_score = self._find_best_match(embedding, now)

        if matched_id is not None:
            # RE-ENTRY: same physical person returning
            self._reentry_count += 1
            visitor_id = matched_id
            entry = self._gallery[visitor_id]
            entry.exit_time = None        # Re-open the session
            entry.last_seen_ts = now
            if embedding is not None:
                # Update embedding with latest appearance (EMA update)
                if entry.embedding is not None:
                    alpha = 0.3
                    updated = alpha * embedding + (1 - alpha) * entry.embedding
                    norm = np.linalg.norm(updated)
                    entry.embedding = updated / norm if norm > 1e-8 else embedding
                else:
                    entry.embedding = embedding
            entry.session_seq += 1
            event_type = EventType.REENTRY.value
            logger.debug("reentry_detected",
                         visitor_id=visitor_id,
                         track_id=detection.track_id,
                         similarity=round(best_score, 3))
        else:
            # ENTRY: brand new visitor
            self._entry_count += 1
            visitor_id = self._new_visitor_id()
            entry = GalleryEntry(
                visitor_id=visitor_id,
                embedding=embedding,
                last_seen_ts=now,
                session_seq=1,
            )
            self._gallery[visitor_id] = entry
            event_type = EventType.ENTRY.value

        # Register track → visitor mapping
        self._track_to_visitor[detection.track_id] = visitor_id

        return TrackedVisitor(
            detection=detection,
            visitor_id=visitor_id,
            event_type=event_type,
            zone_id=None,   # Populated by ZoneMapper downstream
            is_staff=False, # Populated by StaffDetector downstream
            embedding=embedding,
            session_seq=entry.session_seq,
        )

    def mark_exit(self, track_id: int, timestamp: float) -> Optional[str]:
        """
        Record that a track has crossed the exit threshold.
        Enables future re-entry matching for this visitor.

        Returns visitor_id if found, None otherwise.
        """
        visitor_id = self._track_to_visitor.get(track_id)
        if visitor_id and visitor_id in self._gallery:
            self._gallery[visitor_id].exit_time = timestamp
            logger.debug("visitor_exited",
                         visitor_id=visitor_id, track_id=track_id)
            return visitor_id
        return None

    def evict_expired(self, current_ts: float) -> int:
        """
        Remove gallery entries older than the re-entry window.
        Call periodically (e.g., every 1000 frames) to bound memory.
        Returns number of entries evicted.
        """
        window = self.config.reid_gallery_window_sec
        expired = [
            vid for vid, entry in self._gallery.items()
            if entry.exit_time is not None
            and (current_ts - entry.exit_time) > window
        ]
        for vid in expired:
            del self._gallery[vid]
        if expired:
            logger.debug("gallery_evicted", count=len(expired))
        return len(expired)

    def stats(self) -> dict:
        """Return gallery statistics for logging."""
        return {
            "total_gallery_entries": len(self._gallery),
            "active_tracks": len(self._track_to_visitor),
            "entry_count": self._entry_count,
            "reentry_count": self._reentry_count,
            "reentry_rate": round(
                self._reentry_count / max(self._entry_count, 1), 4
            ),
        }

    # ── Private helpers ───────────────────────────────────────────────────────

    def _find_best_match(
        self,
        embedding: Optional[np.ndarray],
        current_ts: float,
    ) -> tuple[Optional[str], float]:
        """
        Find the best matching exited visitor in the gallery.
        Only considers visitors who have exited (exit_time is not None)
        and whose exit was within the re-entry window.

        Returns (visitor_id, similarity_score) or (None, 0.0).
        """
        if embedding is None:
            return None, 0.0

        best_id: Optional[str] = None
        best_score: float = 0.0
        window = self.config.reid_gallery_window_sec
        threshold = self.config.reid_similarity_threshold

        for vid, entry in self._gallery.items():
            # Only match against exited visitors
            if entry.exit_time is None:
                continue
            # Only within re-entry window
            if (current_ts - entry.exit_time) > window:
                continue
            if entry.embedding is None:
                continue

            score = cosine_similarity(embedding, entry.embedding)
            if score > best_score:
                best_score = score
                best_id = vid

        if best_score >= threshold:
            return best_id, best_score
        return None, best_score

    @staticmethod
    def _new_visitor_id() -> str:
        """Generate a visitor ID in the format VIS_<6 hex chars>."""
        return f"VIS_{uuid.uuid4().hex[:6]}"
