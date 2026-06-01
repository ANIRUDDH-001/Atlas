"""
Cross-camera visitor deduplication.

Prevents the same physical person from being counted as multiple visitors
when they appear in overlapping camera fields of view.

Strategy:
1. Maintain a registry of recently seen visitors: visitor_id → embedding + timestamp
2. When a new visitor is about to be assigned a visitor_id in a different camera,
   check if any existing visitor (from another camera) has:
   - A similar appearance embedding (cosine similarity > threshold)
   - Was seen within the dedup time window
3. If match found: use the existing visitor_id (merge identities)
4. If no match: assign new visitor_id normally

This deduplication runs BEFORE the VisitorGallery re-entry check to ensure
cross-camera identity merging takes precedence over re-entry detection.
"""
import structlog
import numpy as np
from dataclasses import dataclass
from typing import Optional

from pipeline.reid import cosine_similarity
from pipeline.config import PipelineConfig

logger = structlog.get_logger()


@dataclass
class CameraObservation:
    """One camera's observation of a visitor."""
    visitor_id: str
    camera_id: str
    embedding: Optional[np.ndarray]
    timestamp: float  # Unix timestamp


class CrossCameraDeduplicator:
    """
    Prevents double-counting visitors across overlapping camera views.

    Maintains a sliding window of recent visitor observations and
    merges identities when high-similarity matches are found across
    different cameras.

    Usage:
        dedup = CrossCameraDeduplicator(config)
        canonical_id = dedup.resolve(visitor_id, camera_id, embedding, timestamp)
        # canonical_id may differ from visitor_id if a cross-camera match was found
    """

    def __init__(self, config: PipelineConfig):
        self._config = config
        self._threshold = config.cross_camera_similarity_threshold
        # Registry: visitor_id → CameraObservation
        self._registry: dict[str, CameraObservation] = {}
        # Merge map: alias_visitor_id → canonical_visitor_id
        self._merge_map: dict[str, str] = {}
        self._dedup_count = 0

    def resolve(
        self,
        visitor_id: str,
        camera_id: str,
        embedding: Optional[np.ndarray],
        timestamp: float,
    ) -> str:
        """
        Resolve a visitor_id to the canonical cross-camera identity.

        Args:
            visitor_id: The visitor_id assigned by VisitorGallery for this camera
            camera_id: The camera that produced this observation
            embedding: The appearance embedding for this visitor (may be None)
            timestamp: Unix timestamp of this observation

        Returns:
            The canonical visitor_id to use for all events from this person.
            This may be the same as visitor_id (no cross-camera match)
            or a different visitor_id from another camera (merged).
        """
        # Evict expired entries
        self._evict_expired(timestamp)

        # Check if visitor_id is already a known alias
        if visitor_id in self._merge_map:
            canonical = self._merge_map[visitor_id]
            logger.debug("dedup_alias_resolved",
                         alias=visitor_id, canonical=canonical)
            return canonical

        # Search for a cross-camera match
        if embedding is not None:
            match = self._find_cross_camera_match(
                visitor_id, camera_id, embedding, timestamp
            )
            if match is not None:
                # Merge: visitor_id is an alias for the matching canonical ID
                self._merge_map[visitor_id] = match
                self._dedup_count += 1
                logger.info("cross_camera_dedup",
                            alias=visitor_id,
                            canonical=match,
                            camera=camera_id)
                return match

        # No match — register this observation as a new canonical entry
        self._registry[visitor_id] = CameraObservation(
            visitor_id=visitor_id,
            camera_id=camera_id,
            embedding=embedding,
            timestamp=timestamp,
        )
        return visitor_id

    def stats(self) -> dict:
        return {
            "registry_size": len(self._registry),
            "merge_count": self._dedup_count,
            "alias_count": len(self._merge_map),
        }

    # ── Private helpers ───────────────────────────────────────────────────────

    def _find_cross_camera_match(
        self,
        visitor_id: str,
        camera_id: str,
        embedding: np.ndarray,
        timestamp: float,
    ) -> Optional[str]:
        """
        Find a registry entry from a different camera with similar appearance.
        Returns the canonical visitor_id if match found, else None.
        """
        best_id: Optional[str] = None
        best_score: float = 0.0

        for reg_vid, obs in self._registry.items():
            # Only match across different cameras
            if obs.camera_id == camera_id:
                continue
            # Only within the dedup time window
            if (timestamp - obs.timestamp) > self._config.cross_camera_dedup_window_sec:
                continue
            if obs.embedding is None:
                continue

            score = cosine_similarity(embedding, obs.embedding)
            if score > best_score:
                best_score = score
                best_id = reg_vid

        if best_score >= self._threshold:
            return best_id
        return None

    def _evict_expired(self, current_ts: float) -> None:
        """Remove entries outside the dedup window."""
        expired = [
            vid for vid, obs in self._registry.items()
            if (current_ts - obs.timestamp) > self._config.cross_camera_dedup_window_sec * 2
        ]
        for vid in expired:
            del self._registry[vid]
