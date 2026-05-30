"""
YOLO11n + BoT-SORT person detection and tracking.
"""
import cv2
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Generator

import structlog
from ultralytics import YOLO

from pipeline.types import Detection
from pipeline.config import PipelineConfig

logger = structlog.get_logger()


# Entry/exit direction detection via a virtual crossing line
# Persons crossing from top-to-bottom = ENTRY; bottom-to-top = EXIT
# The threshold_y is normalised (0.0–1.0) relative to frame height
DIRECTION_HISTORY: dict[int, list[float]] = {}  # track_id → [cy_history]


class Detector:
    """
    Wraps YOLO11n + BoT-SORT for single-clip inference.

    Usage:
        detector = Detector(config)
        for detection in detector.process_clip(path, store_id, camera_id, start_ts):
            handle(detection)
    """

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.model = YOLO("yolo11n.pt")   # Downloads on first run
        self.model.fuse()                  # Fuse layers for CPU speedup
        logger.info("detector_initialized",
                    model="yolo11n",
                    tracker=config.tracker_type,
                    conf=config.detection_conf)

    def process_clip(
        self,
        video_path: Path,
        store_id: str,
        camera_id: str,
        clip_start_time: datetime,
    ) -> Generator[Detection, None, None]:
        """
        Process a single video clip. Yields one Detection per
        tracked person per processed frame.

        Args:
            video_path: Absolute path to the video file
            store_id: Store identifier from store_layout.json
            camera_id: Camera identifier from store_layout.json
            clip_start_time: UTC datetime of the first frame in the clip

        Yields:
            Detection objects for every track in every processed frame

        Raises:
            FileNotFoundError: if video_path does not exist
            RuntimeError: if video cannot be opened by OpenCV
        """
        if not video_path.exists():
            raise FileNotFoundError(f"Video not found: {video_path}")

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open video: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS) or self.config.target_fps
        frame_idx = 0
        processed = 0
        direction_history: dict[int, list[float]] = {}

        logger.info("clip_start", video=str(video_path),
                    camera_id=camera_id, fps=fps)

        try:
            # Run YOLO tracking — persist=True keeps IDs across frames
            for result in self.model.track(
                source=str(video_path),
                stream=True,            # Memory-efficient streaming
                persist=True,           # Consistent track IDs
                tracker=self.config.tracker_type,
                classes=[self.config.person_class_id],
                conf=self.config.detection_conf,
                iou=self.config.detection_iou,
                imgsz=self.config.imgsz,
                verbose=False,
            ):
                # Skip frames if configured
                if frame_idx % self.config.process_every_n_frames != 0:
                    frame_idx += 1
                    continue

                frame_time = clip_start_time + timedelta(
                    seconds=frame_idx / fps
                )

                if result.boxes is None or result.boxes.id is None:
                    frame_idx += 1
                    continue

                for i, box in enumerate(result.boxes):
                    track_id = int(box.id[0])
                    bbox = tuple(box.xyxy[0].cpu().numpy().astype(float))
                    conf = float(box.conf[0].cpu().numpy())

                    # Update direction history (y-centroid)
                    cy = (bbox[1] + bbox[3]) / 2.0 / result.orig_shape[0]
                    if track_id not in direction_history:
                        direction_history[track_id] = []
                    direction_history[track_id].append(cy)
                    # Keep only last 10 positions
                    direction_history[track_id] = direction_history[track_id][-10:]

                    yield Detection(
                        track_id=track_id,
                        bbox=bbox,
                        confidence=conf,
                        frame_idx=frame_idx,
                        timestamp=frame_time,
                        camera_id=camera_id,
                    )
                    processed += 1

                frame_idx += 1

        finally:
            cap.release()
            logger.info("clip_complete", video=str(video_path),
                        frames_processed=frame_idx,
                        detections_yielded=processed)

    def get_direction(
        self,
        track_id: int,
        threshold_y: float = 0.5,
    ) -> str | None:
        """
        Determine if a track is crossing the entry threshold.

        Args:
            track_id: The BoT-SORT track identifier
            threshold_y: Normalised Y coordinate of the entry line (0.0–1.0)

        Returns:
            "ENTRY" if crossing inbound (top → bottom)
            "EXIT" if crossing outbound (bottom → top)
            None if no crossing detected
        """
        history = DIRECTION_HISTORY.get(track_id, [])
        if len(history) < 3:
            return None

        recent = history[-3:]
        prev_above = recent[0] < threshold_y
        curr_below = recent[-1] >= threshold_y

        if prev_above and curr_below:
            return "ENTRY"
        if not prev_above and not curr_below:
            return "EXIT"
        return None

    def get_frame_embedding_crop(
        self,
        frame: np.ndarray,
        bbox: tuple,
    ) -> np.ndarray | None:
        """
        Crop the person region from a frame for Re-ID embedding.
        Returns the BGR crop, or None if crop is invalid.
        """
        x1, y1, x2, y2 = map(int, bbox)
        x1, y1 = max(0, x1), max(0, y1)
        x2 = min(frame.shape[1], x2)
        y2 = min(frame.shape[0], y2)

        if x2 <= x1 or y2 <= y1:
            return None
        return frame[y1:y2, x1:x2]
