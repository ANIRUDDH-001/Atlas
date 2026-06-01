import json
from pathlib import Path

events = [json.loads(line) for line in
          Path("data/events.jsonl").read_text().splitlines() if line.strip()]

reentry_count = sum(1 for e in events if e['event_type'] == 'REENTRY')
entry_count   = sum(1 for e in events if e['event_type'] == 'ENTRY' and not e['is_staff'])
total_visitors = len(set(e['visitor_id'] for e in events
                         if not e['is_staff'] and e['event_type'] in ('ENTRY','REENTRY')))

print(f"ENTRY events:   {entry_count}")
print(f"REENTRY events: {reentry_count}")
print(f"Total visitors: {total_visitors}")
if entry_count > 0:
    print(f"Re-entry rate:  {reentry_count/entry_count:.1%}")
else:
    print("Re-entry rate: N/A (no entries)")
