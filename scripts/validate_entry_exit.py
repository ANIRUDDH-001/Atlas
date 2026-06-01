import json
from pathlib import Path

events = [json.loads(line) for line in
          Path("data/events.jsonl").read_text().splitlines() if line.strip()]

entry_cam = [e for e in events if e['camera_id'] == 'CAM_ENTRY_01']
entries = sum(1 for e in entry_cam if e['event_type'] == 'ENTRY')
exits   = sum(1 for e in entry_cam if e['event_type'] == 'EXIT')

print(f"CAM_ENTRY_01: ENTRY={entries}, EXIT={exits}")
if entries > 0:
    print(f"Balance ratio: {exits/entries:.2f}")
else:
    print("Balance ratio: N/A (no entries)")
