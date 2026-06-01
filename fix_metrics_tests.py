import uuid
import re

with open('tests/test_metrics.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix stale_event
content = re.sub(r'"event_id": "test-stale-queue-001",', f'"event_id": "{uuid.uuid4()}",', content)
content = re.sub(r'"queue_depth": 15,(\s*)"is_staff"', r'"metadata": {"queue_depth": 15, "session_seq": 1},\1"is_staff"', content)

# Fix test-conf events
content = re.sub(r'"event_id": f"test-conf-\{i:03d\}",', '"event_id": str(uuid.uuid4()),', content)
# Replace queue_depth=None with metadata
content = content.replace('"queue_depth": None,', '"metadata": {"queue_depth": None, "session_seq": 1},')

# Fix test-staff-001
content = re.sub(r'"event_id": "test-staff-001",', f'"event_id": "{uuid.uuid4()}",', content)

# Fix test-reentry-001 and 002
content = re.sub(r'"event_id": "test-reentry-001",', f'"event_id": "{uuid.uuid4()}",', content)
content = re.sub(r'"event_id": "test-reentry-002",', f'"event_id": "{uuid.uuid4()}",', content)

with open('tests/test_metrics.py', 'w', encoding='utf-8') as f:
    if 'import uuid' not in content:
        content = 'import uuid\n' + content
    f.write(content)
