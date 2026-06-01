from pathlib import Path
from datetime import datetime, timezone
from pipeline.config import get_pipeline_config
from pipeline.detect import Detector
import collections
import sys

camera_id = sys.argv[1]
video_file = sys.argv[2]
test_conf = float(sys.argv[3])

config = get_pipeline_config()
config.detection_conf = test_conf

detector = Detector(config)
event_counts = collections.Counter()  # type: ignore

for det in detector.process_clip(
    Path(video_file),
    "STORE_ST1008", camera_id,
    datetime.now(timezone.utc)
):
    event_counts['total'] += 1
    if det.confidence < 0.35:
        event_counts['low_conf'] += 1

print(f"Total detections: {event_counts['total']}")
print(f"Low confidence (<0.35): {event_counts['low_conf']}")
print(f"Ratio: {event_counts['low_conf']/max(event_counts['total'],1):.2%}")
