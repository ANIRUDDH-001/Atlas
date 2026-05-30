# Engineering Decisions — CHOICES.md

Three key engineering decisions made during this challenge, with full
reasoning including options considered, AI suggestions, and overrides.

---

## Decision 1: Detection Model and Tracker Selection

### The Problem
Choose the computer vision stack that maximises detection accuracy and
tracking quality for the Brigade Road store's 5 CCTV cameras while
remaining deployable via `docker compose up` on commodity hardware.

### Options Considered

| Option | mAP (COCO) | CPU Inference | Re-ID Built-in | Notes |
|---|---|---|---|---|
| YOLOv8n | 37.3 | ~45ms/frame | No | Well-tested baseline |
| YOLO11n | 39.5 | ~38ms/frame | Yes (via ultralytics) | Newer, 22% fewer params |
| RT-DETR-L | 53.0 | ~420ms/frame | No | Too slow for 30fps clips |
| YOLOv8m | 50.2 | ~180ms/frame | No | Accuracy gain, CPU cost |

For tracking:
- **ByteTrack:** Association by IoU only; no appearance model
- **BoT-SORT:** IoU + camera motion compensation + optional ReID
- **StrongSORT:** AFLink + GSI interpolation; slightly more complex setup

### What AI Suggested
Claude recommended RT-DETR-L, citing its transformer-based global attention
mechanism as superior for partial occlusion scenarios (billing queue scenes).
GPT-4 concurred, adding that YOLOv8 was "dated" for 2026.

### What I Chose: YOLO11n + BoT-SORT (with ReID enabled)

**Override reasoning:**

1. **Hardware constraint is real, not hypothetical.** The acceptance gate requires
   `docker compose up` to start without error on any reviewer's machine. RT-DETR-L
   requires 8GB+ VRAM. A CPU fallback for RT-DETR-L runs at ~420ms per frame —
   on 30fps source footage, this is 12.6× real-time slowdown, making a 2.5-minute
   clip take 31 minutes to process. YOLO11n on CPU runs at ~38ms/frame (1.1×
   real-time at 30fps) — reviewers can run the pipeline end-to-end in the same
   session as `docker compose up`.

2. **The accuracy gap is acceptable for this dataset.** The clips are ~2.5 minutes
   each with relatively low concurrent density (typical retail peak: 3–6 people
   simultaneously). At this density, YOLO11n's mAP of 39.5 is sufficient. RT-DETR-L's
   advantage is most pronounced in dense crowd scenarios (concerts, stadiums) —
   not a beauty retail environment with 5 staff and occasional customers.

3. **BoT-SORT over ByteTrack:** The Brigade Road store cameras have some vibration
   (fixed ceiling mounts, HVAC). BoT-SORT's camera motion compensation (sparse
   optical flow GMC) prevents vibration-induced false ID switches. ByteTrack's
   pure-IoU association would misidentify the same person as different tracks if
   the camera shifts 2–3 pixels between frames. BoT-SORT over StrongSORT: lower
   dependency complexity (built into ultralytics) and StrongSORT's AFLink adds
   ~15ms per frame with diminishing returns at this density.

**What would change this decision:** If the store had 20+ concurrent customers
(festival season, sale events), RT-DETR-L with a GPU-enabled Docker image would
be the correct choice. YOLO11m would be the CPU-viable upgrade path.

---

## Decision 2: Event Schema Design Rationale

### The Problem
Design the event schema that serves three conflicting constraints:
(a) Pipeline emission: each event must be writable per-detection
(b) API reads: queries aggregate across events efficiently
(c) Business logic: conversion rate requires session-level deduplication

### Options Considered

**Option A: Session-centric schema**
One record per visitor session with embedded event arrays.
```json
{ "visitor_id": "VIS_a3f7c1", "store_id": "ST1008",
  "events": [{"type":"ENTRY","ts":"..."}, {"type":"ZONE_ENTER","ts":"..."}] }
```
Pros: Deduplication trivial (one row = one session). Cons: Pipeline must buffer
all events for a visitor before writing. Re-entry detection breaks because the
session never closes cleanly until exit.

**Option B: Event-centric schema (chosen)**
One record per event, session identity via `visitor_id`.
```json
{ "event_id": "uuid", "visitor_id": "VIS_a3f7c1", "event_type": "ZONE_ENTER",
  "zone_id": "SKINCARE", "session_seq": 3, ... }
```
Pros: Pipeline emits immediately per detection (no buffering). Replay-safe
(idempotent by `event_id`). Sessions reconstructed at query time with GROUP BY
visitor_id. Cons: Conversion queries require a JOIN with POS data.

**Option C: Pre-aggregated summary table**
Pipeline writes both raw events and a running session summary.
Pros: Fast reads. Cons: Write amplification; summary becomes stale if events
arrive out of order (common in multi-camera scenarios).

### What AI Suggested
Claude suggested adding a `session_id` field separate from `visitor_id`, arguing
that "the same visitor could have multiple sessions across days." GPT-4 suggested
a `raw_bbox` field for auditability.

### What I Chose: Event-centric (Option B) without separate session_id and without raw_bbox

**Override reasoning:**

1. **No separate session_id.** In this system, session = visitor_id + date. A visitor
   returning on a different day gets a new entry in the `VisitorGallery` (30-minute
   window means it expired). Adding a `session_id` field creates a join key that
   the API would never use — all queries filter by `visitor_id` using `DISTINCT`.
   The indirection adds storage and complexity with zero query benefit.

2. **No raw_bbox.** Bounding boxes are needed only during pipeline processing for
   zone mapping and embedding extraction. After those two uses, the bbox provides
   no business value. Storing 4 floats per event across thousands of events adds
   ~40% storage overhead for data that no endpoint reads. Reviewers checking
   `/metrics` will never see bbox data — it costs more than it earns.

3. **`session_seq` was AI-suggested and kept.** Claude identified that the funnel
   deduplication query (which visitor reached billing) benefits from event ordering
   within a session. `session_seq` is a 1-based counter that makes session ordering
   free at query time. This suggestion was correct and incorporated.

**Brigade Road implication:** With ~2.5-minute clips, each visitor session is
fully contained within one clip. Session reconstruction via GROUP BY visitor_id
is computationally trivial at this scale.

---

## Decision 3: API Storage Architecture

### The Problem
Choose the data layer for the Intelligence API: what stores events, what
serves metrics, and how to handle the zero-latency requirement for the
live dashboard SSE stream.

### Options Considered

| Option | Write Latency | Read Latency | Complexity | Consistency |
|---|---|---|---|---|
| SQLite only | ~2ms | ~15ms | Very low | Single-writer limit |
| PostgreSQL only | ~3ms | ~8ms | Medium | Full ACID |
| PostgreSQL + Redis cache | ~3ms | ~0.5ms (cache hit) | Medium | Eventual (30s stale) |
| TimescaleDB | ~3ms | ~5ms | High | Full, time-optimised |

### What AI Suggested
Claude suggested TimescaleDB, citing native time-series compression and
built-in continuous aggregates for real-time metrics. It argued the
`events` table is fundamentally time-series data and should use a
time-series database.

GPT-4 suggested SQLite for simplicity, noting "the dataset is small."

### What I Chose: PostgreSQL 16 + Redis 7 (dual layer)

**Override reasoning:**

1. **Against TimescaleDB:** The Brigade Road dataset has 24 invoices and ~2.5
   minutes of video per camera. At this scale, TimescaleDB's continuous aggregate
   feature provides zero measurable benefit — all metric queries complete in <10ms
   on vanilla PostgreSQL with the right indexes. TimescaleDB adds a separate
   installation, additional Docker layer complexity, and a steeper debugging surface.
   The `docker compose up` acceptance gate would require reviewers to pull a
   larger, less standard image. TimescaleDB becomes the correct choice at 40 live
   stores emitting thousands of events per minute in real-time — not for a batch
   pipeline on 5 clips totalling 12.5 minutes.

2. **Against SQLite:** SQLite's single-writer limitation breaks the pipeline
   replay scenario. When `scripts/ingest_events.py` batches events from
   `events.jsonl`, the API must accept concurrent POST requests while potentially
   serving GET requests for the dashboard SSE stream. SQLite's write lock would
   cause the SSE stream to block during ingest. PostgreSQL's MVCC (multi-version
   concurrency control) handles this natively.

3. **For Redis cache layer:** The SSE stream polls `compute_metrics()` every 5
   seconds for each connected dashboard client. Without caching, each SSE tick
   triggers 5 separate SQL queries (visitors, conversions, dwell, queue, abandonment).
   With Redis: first call computes and caches for 30 seconds; subsequent ticks
   serve from memory in <1ms. For the Brigade Road dataset with 24 transactions,
   the 30-second TTL means cached metrics are never more than 30s stale —
   perfectly adequate for operational decision-making.

**The trade-off I accepted:** Redis introduces a 30-second eventual consistency
window. If a new event is ingested and a reviewer immediately calls `/metrics`,
they may see a cached response. Mitigation: cache is invalidated on every
`POST /events/ingest` for the affected store. So the staleness window only
applies to background events — not to events just ingested via the API.

**What would change this decision:** At 40 live stores with real-time streaming
pipelines (not batch), PostgreSQL read replicas and TimescaleDB continuous
aggregates would be the correct architecture. Redis would scale to a cluster.
The current dual-layer design is the minimum viable production stack that
demonstrates the correct architectural pattern without over-engineering a
hackathon submission.
