#!/usr/bin/env python3
"""
Ingest events.jsonl into the running Store Intelligence API.

Usage:
    python3 scripts/ingest_events.py
    python3 scripts/ingest_events.py --api http://localhost:8000
    python3 scripts/ingest_events.py --file data/events.jsonl --batch-size 100
"""
import json
import argparse
import time
import sys
from pathlib import Path

try:
    import httpx
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "httpx", "-q"])
    import httpx


def batched(iterable, n):
    """Split iterable into chunks of size n."""
    it = iter(iterable)
    while True:
        batch = []
        try:
            for _ in range(n):
                batch.append(next(it))
        except StopIteration:
            if batch:
                yield batch
            break
        yield batch


def ingest_events(api_base: str, events_file: Path, batch_size: int):
    lines = events_file.read_text().strip().splitlines()
    events = [json.loads(l) for l in lines if l.strip()]

    print(f"Ingesting {len(events)} events in batches of {batch_size}")
    print(f"API: {api_base}")
    print(f"File: {events_file}")
    print("-" * 50)

    total_accepted = 0
    total_rejected = 0
    batch_num = 0

    for batch in batched(events, batch_size):
        batch_num += 1
        try:
            r = httpx.post(
                f"{api_base}/events/ingest",
                json={"events": batch},
                timeout=30,
            )
            if r.status_code == 200:
                body = r.json()
                total_accepted += body.get("accepted", 0)
                total_rejected += body.get("rejected", 0)
                print(f"Batch {batch_num:3d}: accepted={body['accepted']:4d} "
                      f"rejected={body['rejected']:3d}")
                if body.get("errors"):
                    for err in body["errors"][:3]:
                        print(f"  ERROR: {err['event_id']}: {err['reason']}")
            else:
                print(f"Batch {batch_num:3d}: HTTP {r.status_code} — {r.text[:100]}")
        except httpx.ConnectError:
            print(f"ERROR: Cannot connect to {api_base}")
            print("Make sure the API is running: docker compose up -d")
            sys.exit(1)
        except Exception as e:
            print(f"Batch {batch_num}: ERROR — {e}")

        time.sleep(0.1)  # Gentle rate — don't overwhelm the API

    print("-" * 50)
    print(f"INGEST COMPLETE")
    print(f"  Total events: {len(events)}")
    print(f"  Accepted:     {total_accepted}")
    print(f"  Rejected:     {total_rejected}")
    print(f"\nVerify: curl http://localhost:8000/stores/STORE_ST1008/metrics | python3 -m json.tool")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--api",        default="http://localhost:8000")
    parser.add_argument("--file",       default="data/events.jsonl", type=Path)
    parser.add_argument("--batch-size", default=200, type=int)
    args = parser.parse_args()

    if not args.file.exists():
        print(f"ERROR: {args.file} not found.")
        print("Run the pipeline first: bash pipeline/run.sh")
        sys.exit(1)

    ingest_events(args.api, args.file, args.batch_size)
