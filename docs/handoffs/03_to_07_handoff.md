# Handoff: CV Pipeline → Testing / QA

## What the Testing Agent Needs

### Pipeline Testability
The pipeline is batch-mode — tests do not need live video. Use:
1. `tests/fixtures/sample_events.jsonl` — already valid events to ingest
2. `pipeline/emit.py` `EventEmitter` — unit-testable with a temp file
3. `pipeline/tracker.py` `VisitorGallery` — unit-testable with mock embeddings
4. `pipeline/direction.py` `DirectionDetector` — unit-testable with synthetic Y positions
5. `pipeline/staff_detector.py` `StaffDetector` — unit-testable with synthetic frames

### Critical Test Cases Required (Part A scoring)
1. Group entry: 3 track_ids crossing simultaneously → 3 ENTRY events
2. Re-entry: mark_exit → similar embedding → REENTRY event
3. Staff exclusion: is_staff=True on events with purple upper body
4. Empty periods: Detector yields 0 detections → 0 events written
5. Schema compliance: every emitted event validates against StoreEvent

### Schema Validation Helper
```python
from app.models import StoreEvent
import json

def validate_events_file(path: str) -> tuple[int, int]:
    valid, invalid = 0, 0
    for line in open(path):
        try:
            StoreEvent(**json.loads(line))
            valid += 1
        except Exception:
            invalid += 1
    return valid, invalid
```

### Prompt Block Header Required in test_pipeline.py
```python
# PROMPT: "Generate pytest tests for the CV pipeline covering:
#  1. VisitorGallery re-entry detection with mock embeddings
#  2. DirectionDetector ENTRY/EXIT/group crossing
#  3. EventEmitter zone transition and ZONE_DWELL timing
#  4. StoreEvent schema validation of events.jsonl output
# Use pytest-asyncio, tmp_path fixture, and unittest.mock for ReIDExtractor."
# CHANGES MADE: <fill in after generation>
```
