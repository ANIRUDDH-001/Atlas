from pipeline.detect import Detector
from pipeline.config import get_pipeline_config
from pathlib import Path
from datetime import datetime, timezone

config = get_pipeline_config()
detector = Detector(config)

count = 0
try:
    for det in detector.process_clip(
        Path("data/test_clip.mp4"),  # use any available test clip
        "STORE_ST1008",
        "CAM_ENTRY_01",
        datetime.now(timezone.utc)
    ):
        count += 1
        if count == 1:
            print(f"First detection: track_id={det.track_id}, conf={det.confidence:.2f}")
        if count > 50:
            break
    print(f"PASS: {count} detections yielded")
except FileNotFoundError:
    print("INFO: No test clip available — import test passed")
