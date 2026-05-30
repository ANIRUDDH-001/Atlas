# Handoff: Backend → CV Pipeline Engineering

## What the Backend Expects from the Pipeline

### Output file
The pipeline must write events to the path defined by:
`settings.pipeline_output_path` (default: `./data/events.jsonl`)

One JSON object per line. Every line must be a valid `StoreEvent` as
defined in `app/models.py`.

### Required event_type values
All 8 types in `app/constants.EventType` must be emittable by the pipeline:
ENTRY, EXIT, ZONE_ENTER, ZONE_EXIT, ZONE_DWELL, BILLING_QUEUE_JOIN,
BILLING_QUEUE_ABANDON, REENTRY

### visitor_id format
Must start with `VIS_` followed by 6 hex characters. Example: `VIS_c8a2f1`

### timestamp format
ISO-8601 UTC with Z suffix. Example: `2026-03-03T14:22:10Z`
Derived from: clip start datetime + (frame_index / fps) seconds.

### confidence field
Must be emitted even for low-confidence detections (never suppress).
Range: 0.0 to 1.0 inclusive.

### is_staff field
Must be classified per event. The API excludes `is_staff=true` events
from all customer metrics. Misclassification directly inflates visitor counts.

### zone_id rules
- ENTRY, EXIT, REENTRY: zone_id MUST be null
- ZONE_ENTER, ZONE_EXIT, ZONE_DWELL: zone_id MUST be non-null
- Zone names must match keys in store_layout.json exactly

### metadata.queue_depth
Only required for BILLING_QUEUE_JOIN events. Must be an integer >= 0.
For all other events, set to null.

### metadata.session_seq
1-based ordinal: first event for a visitor in a session = 1,
next event = 2, etc. Never 0.

## How to Ingest Pipeline Output into the API
```bash
# Process all clips
bash pipeline/run.sh

# Ingest output into the running API (batch in chunks of 500)
python3 - <<'EOF'
import json, httpx, itertools

def batched(iterable, n):
    it = iter(iterable)
    while batch := list(itertools.islice(it, n)):
        yield batch

events = [json.loads(l) for l in open("data/events.jsonl").read().splitlines()]
for batch in batched(events, 500):
    r = httpx.post("http://localhost:8000/events/ingest",
                   json={"events": batch}, timeout=30)
    print(r.json())
EOF
```

## What Must Not Change
- `StoreEvent` schema field names or types
- Endpoint paths
- `visitor_id` format (`VIS_` prefix + 6 hex)
