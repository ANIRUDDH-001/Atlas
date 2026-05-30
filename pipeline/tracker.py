"""
Visitor gallery and Re-ID for cross-frame identity persistence.

Implemented fully in: 03_04_osnet_reid.md + 03_05_visitor_gallery.md
"""
from pipeline.types import Detection, TrackedVisitor
from pipeline.config import PipelineConfig


class VisitorGallery:
    """Maintains rolling appearance embeddings for re-entry detection."""

    def __init__(self, config: PipelineConfig):
        ...

    def resolve(
        self, detection: Detection, embedding
    ) -> TrackedVisitor:
        """
        Given a detection and its embedding, return a TrackedVisitor
        with the correct visitor_id and event_type (ENTRY or REENTRY).
        """
        ...

    def mark_exit(self, track_id: int, timestamp) -> None:
        """Record that a track has exited, enabling future re-entry matching."""
        ...
