"""
YOLO11n + BoT-SORT person detection and tracking.

Processes a single video clip and yields TrackedVisitor objects per frame.
Implemented fully in: 03_02_yolo11_detection.md
"""
from pathlib import Path
from typing import Generator
from pipeline.types import Detection, StoreLayout
from pipeline.config import PipelineConfig


class Detector:
    """Wraps YOLO11n + BoT-SORT for per-clip inference."""

    def __init__(self, config: PipelineConfig):
        ...

    def process_clip(
        self,
        video_path: Path,
        store_id: str,
        camera_id: str,
        clip_start_time,
    ) -> Generator[Detection, None, None]:
        """
        Yield one Detection per tracked person per processed frame.
        Raises: FileNotFoundError if video_path does not exist.
        """
        ...
