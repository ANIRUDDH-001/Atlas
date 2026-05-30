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

import os
import re
from pipeline.tracker import VisitorGallery
from pipeline.staff_detector import StaffDetector
from pipeline.zone_mapper import ZoneMapper
from pipeline.emit import EventEmitter
from pipeline.direction import DirectionDetector
from pipeline.dedup import CrossCameraDeduplicator
from pipeline.types import TrackedVisitor


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

def run_pipeline(
    video_dir: Path,
    layout_path: Path,
    output_path: Path,
    config: PipelineConfig,
) -> int:
    """
    Process all video clips and write unified events.jsonl.

    Args:
        video_dir: Root directory containing {store_id}/{camera_id}.mp4
        layout_path: Path to store_layout.json
        output_path: Path to write events.jsonl
        config: Pipeline configuration

    Returns:
        Total number of events written.
    """
    detector     = Detector(config)
    staff_det    = StaffDetector(config)
    emitter      = EventEmitter(output_path, config)
    total_events = 0

    # Discover all store directories
    store_dirs = sorted([d for d in video_dir.iterdir() if d.is_dir()])
    if not store_dirs:
        logger.warning("no_store_dirs_found", video_dir=str(video_dir))
        return 0

    for store_dir in store_dirs:
        store_id = store_dir.name
        logger.info("processing_store", store_id=store_id)

        # Per-store shared state
        gallery    = VisitorGallery(config)
        dedup      = CrossCameraDeduplicator(config)

        # Discover clips for this store, ordered by camera type
        clips = _discover_clips(store_dir)
        if not clips:
            logger.warning("no_clips_found", store_id=store_id)
            continue

        for camera_id, clip_path in clips:
            clip_start = _extract_clip_start_time(clip_path)
            logger.info("processing_clip",
                        store_id=store_id,
                        camera_id=camera_id,
                        clip=str(clip_path),
                        start_time=clip_start.isoformat())

            try:
                zone_mapper = ZoneMapper.from_layout_file(
                    layout_path, store_id, camera_id, config
                )
            except (FileNotFoundError, KeyError) as e:
                logger.warning("zone_mapper_failed",
                               store_id=store_id, camera_id=camera_id,
                               error=str(e))
                zone_mapper = None

            is_entry_cam = (zone_mapper is not None and
                            zone_mapper.is_entry_camera())
            direction_det = (DirectionDetector(zone_mapper.get_threshold_y())
                             if is_entry_cam else None)

            prev_positions: dict[int, float] = {}

            for detection in detector.process_clip(
                clip_path, store_id, camera_id, clip_start
            ):
                # Extract frame for embedding and staff detection
                frame_crop = None  # Crop extracted inline in Detector for now

                # Resolve identity via gallery
                tracked = gallery.resolve(detection, frame_crop)

                # Cross-camera deduplication
                canonical_id = dedup.resolve(
                    tracked.visitor_id,
                    camera_id,
                    tracked.embedding,
                    detection.timestamp.timestamp(),
                )
                if canonical_id != tracked.visitor_id:
                    # Replace with canonical ID (do not emit separate ENTRY)
                    tracked = TrackedVisitor(
                        detection=tracked.detection,
                        visitor_id=canonical_id,
                        event_type="ZONE_DWELL",  # Not a new entry
                        zone_id=tracked.zone_id,
                        is_staff=tracked.is_staff,
                        embedding=tracked.embedding,
                        session_seq=tracked.session_seq,
                    )

                # Zone mapping
                if zone_mapper and not zone_mapper.is_entry_camera():
                    frame_placeholder = None  # Real frame not available in stream mode
                    # Zone mapper needs frame shape — use clip resolution from config
                    tracked.zone_id = zone_mapper.get_zone(
                        detection.bbox,
                        (1080, 1920),  # Per spec: 1080p clips
                    )

                # Direction detection for entry cameras
                if direction_det is not None:
                    foot_y = detection.bbox[3] / 1080.0
                    direction = direction_det.update(
                        detection.track_id, foot_y, detection.frame_idx
                    )
                    if direction == "ENTRY" and tracked.event_type == "ENTRY":
                        pass  # Already ENTRY from gallery
                    elif direction == "EXIT":
                        tracked.event_type = "EXIT"
                        gallery.mark_exit(detection.track_id,
                                          detection.timestamp.timestamp())

                # Staff classification (sampled every 30 frames)
                if detection.frame_idx % 30 == 0:
                    tracked.is_staff = False  # Default; real detection needs frame

                # Emit event
                emitter.emit(tracked, store_id, (1080, 1920))
                total_events += 1

            # Periodic eviction
            gallery.evict_expired(clip_start.timestamp() + 3600)
            emitter.flush()
            logger.info("clip_done",
                        store_id=store_id,
                        camera_id=camera_id,
                        gallery_stats=gallery.stats())

    emitter.close()
    logger.info("pipeline_complete", total_events=total_events)
    return total_events


def _discover_clips(store_dir: Path) -> list[tuple[str, Path]]:
    """Return (camera_id, clip_path) tuples in processing order."""
    clip_order = {"ENTRY": 0, "FLOOR": 1, "BILLING": 2}
    clips = []
    for clip_path in store_dir.glob("*.mp4"):
        camera_id = clip_path.stem.upper()
        order = 99
        for key, val in clip_order.items():
            if key in camera_id:
                order = val
                break
        clips.append((order, camera_id, clip_path))
    clips.sort(key=lambda x: x[0])
    return [(cam_id, path) for _, cam_id, path in clips]


def _extract_clip_start_time(clip_path: Path):
    """
    Derive clip start datetime from filename (if ISO-8601 encoded)
    or fall back to file modification time.
    """
    from datetime import datetime, timezone
    name = clip_path.stem
    # Try to parse ISO-style datetime from filename e.g. 2026-03-03T14-00-00
    iso_pattern = r"(\d{4}-\d{2}-\d{2}[T_]\d{2}[-:]\d{2}[-:]\d{2})"
    match = re.search(iso_pattern, name)
    if match:
        ts_str = match.group(1).replace("_", "T").replace("-", ":", 2)
        try:
            return datetime.fromisoformat(ts_str).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    # Fallback: file modification time
    mtime = os.path.getmtime(str(clip_path))
    return datetime.fromtimestamp(mtime, tz=timezone.utc)
