"""Pipeline-specific configuration."""
import os
from pathlib import Path
from dataclasses import dataclass, field

@dataclass
class PipelineConfig:
    # Video processing
    target_fps: int = 15          # Native clip fps (from spec)
    process_every_n_frames: int = 1  # Process every frame (set >1 to skip)
    imgsz: int = 640              # YOLO inference size

    # Detection
    detection_conf: float = 0.45  # YOLO confidence threshold
    detection_iou: float = 0.45   # NMS IoU threshold
    person_class_id: int = 0      # COCO class 0 = person

    # Minimum track lifespan (suppress short-lived tracks)
    min_track_frames: int = 5

    # Static object suppression
    static_suppress_frames: int = 90
    static_suppress_px: float = 15.0

    # Minimum bounding box area in pixels
    min_bbox_area: int = 3000

    # Tracking
    tracker_type: str = "pipeline/botsort_retail.yaml"
    track_buffer: int = 45        # Frames before track is lost

    # Re-ID
    reid_model: str = "osnet_x0_25_msmt17.pt"
    reid_similarity_threshold: float = 0.72
    reid_gallery_window_sec: int = 1800  # 30-min re-entry window

    # Staff detection
    staff_hue_lower: int = 130
    staff_hue_upper: int = 160
    staff_saturation_lower: int = 50
    staff_black_value_upper: int = 60
    staff_black_sat_upper: int = 80
    staff_color_ratio_threshold: float = 0.35

    # Zone dwell
    dwell_emit_interval_sec: int = 30

    # Output
    output_path: str = "./data/events.jsonl"
    store_layout_path: str = "./data/store_layout.json"
    pos_csv_path: str = "./data/pos_transactions.csv"


def get_pipeline_config() -> PipelineConfig:
    """Returns PipelineConfig, overridable by environment variables."""
    return PipelineConfig(
        detection_conf=float(os.getenv("PIPELINE_CONF", "0.45")),
        reid_similarity_threshold=float(
            os.getenv("REENTRY_SIMILARITY_THRESHOLD", "0.72")
        ),
        reid_gallery_window_sec=int(
            os.getenv("REENTRY_WINDOW_SECONDS", "1800")
        ),
        output_path=os.getenv("PIPELINE_OUTPUT_PATH", "./data/events.jsonl"),
        store_layout_path=os.getenv("STORE_LAYOUT_PATH", "./data/store_layout.json"),
    )
