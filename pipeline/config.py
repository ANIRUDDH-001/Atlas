"""Pipeline-specific configuration."""
import os
from dataclasses import dataclass

@dataclass
class PipelineConfig:
    target_fps: int = 30  # cameras are 29.97fps (CAMs 1-3) and 24.98fps (CAMs 4-5)
                          # per pipeline/camera_map.json; 30 used as fallback when
                          # OpenCV cannot read fps from container metadata
    process_every_n_frames: int = 1  # Process every frame (set >1 to skip)
    imgsz: int = 640              # YOLO inference size
    default_frame_height: int = 1080  # fallback when OpenCV can't read from container
    default_frame_width: int = 1920

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
    reid_similarity_threshold: float = 0.68
    reid_gallery_window_sec: int = 1800  # 30-min re-entry window

    # Staff detection
    staff_hue_lower: int = 125       # broadened from 130 — fluorescent shifts purple hue
    staff_hue_upper: int = 170       # broadened from 160 — captures desaturated tones
    staff_saturation_lower: int = 30 # lowered from 50 — fluorescent desaturates strongly
    staff_black_value_upper: int = 0
    staff_black_sat_upper: int = 80
    staff_color_ratio_threshold: float = 0.20  # lowered from 0.35 — CCTV crops are 30-60px wide

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
            os.getenv("REENTRY_SIMILARITY_THRESHOLD", "0.68")
        ),
        reid_gallery_window_sec=int(
            os.getenv("REENTRY_WINDOW_SECONDS", "1800")
        ),
        output_path=os.getenv("PIPELINE_OUTPUT_PATH", "./data/events.jsonl"),
        store_layout_path=os.getenv("STORE_LAYOUT_PATH", "./data/store_layout.json"),
    )
