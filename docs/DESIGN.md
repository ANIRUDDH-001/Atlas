# Store Intelligence System — Architecture

## Overview

The Purplle Store Intelligence System is designed to provide actionable offline analytics for Apex Retail across its 40 stores in 8 cities. In a retail environment, understanding customer flow and conversion is as critical as it is in e-commerce. The system processes CCTV video feeds to extract valuable insights regarding customer visits, queue lengths, and zone dwell times. Its core purpose is to drive the North Star Metric: Offline Store Conversion Rate, defined as the ratio of unique purchasers to unique visitors.

To achieve this, the system ingests 20-minute 1080p @ 15fps video clips from 3 cameras per store across 5 initial stores, completely on commodity hardware. Without relying on GPU acceleration for the API layer, paid APIs, or cloud services, this architecture leverages advanced computer vision and a robust data pipeline to correlate physical store behaviour with point-of-sale (POS) transactions. The architecture ensures that offline events are reliably translated into actionable dashboard metrics and real-time anomaly alerts.

## Component Diagram

```text
[CCTV Clips] → [Pipeline: detect.py + tracker.py + emit.py]
                             ↓
                 [events.jsonl on disk]
                             ↓
              [FastAPI POST /events/ingest]
                             ↓
               [PostgreSQL: events table]
               ↕                        ↕
         [Redis cache]       [POS transactions table]
                             ↓
[GET endpoints: /metrics /funnel /heatmap /anomalies /health]
                             ↓
             [SSE stream → React Dashboard]
```

## Stage Descriptions

### Stage 1 — Detection Layer (pipeline/)
The detection layer is responsible for the initial ingestion and processing of video feeds. It takes video file paths and `store_layout.json` as input. Running as a batch process invoked via `pipeline/run.sh`, it uses YOLO11n for person detection and BoT-SORT for robust tracking despite camera motion. An OSNet x0_25 model generates Re-ID embeddings for tracking individuals across frames and cameras. It also performs polygon zone mapping and staff classification via HSV histograms. The structured output is written to `events.jsonl`.

### Stage 2 — Event Stream (events.jsonl)
The structured output from the detection pipeline is stored as an event stream in `events.jsonl`. Each event in the file adheres to a strict schema and is uniquely identified by a UUID v4 `event_id`. This unique key ensures that the stream is replay-safe; the same file can be ingested multiple times idempotently without causing duplicate records in the downstream database.

### Stage 3 — Intelligence API (app/)
The Intelligence API serves as the central data hub. Built with FastAPI and asyncpg, it provides a write path (`/events/ingest`) to insert data into PostgreSQL. The read path utilizes a Redis L1 cache with a 30-second TTL to serve high-frequency dashboard queries, falling back to PostgreSQL on cache misses. The API manages session units by `visitor_id` and performs crucial POS correlation using a 5-minute window join between a visitor's billing zone dwell time and the POS timestamp.

### Stage 4 — Anomaly Engine
The anomaly engine provides proactive alerts based on system state and customer flow. Instead of running as a background job, it is evaluated synchronously on every API read. It detects four primary anomaly types: BILLING_QUEUE_SPIKE, CONVERSION_DROP, DEAD_ZONE, and STALE_FEED. Each anomaly is assigned a severity level (INFO, WARN, or CRITICAL) and includes a `suggested_action` string to guide store staff or management.

### Stage 5 — Live Dashboard
The user interface is a single-page React application hosted without a build step via a CDN, served by an nginx container. It visualizes data using Recharts and connects to the API via Server-Sent Events (SSE) at `GET /stores/{id}/metrics/stream`. The dashboard polls the anomaly engine every 15 seconds to display real-time alerts, ensuring store managers always have the latest insights at their fingertips.

## Technology Decisions

| Concern | Choice | Rationale |
|---|---|---|
| Detection | YOLO11n (ultralytics) | Smallest YOLO11 variant, 22% fewer params than YOLOv8, built-in BoT-SORT, CPU-deployable |
| Tracker | BoT-SORT (via ultralytics) | Camera motion compensation handles CCTV pan/tilt; fallback to ByteTrack if BoT-SORT fails |
| Re-ID | OSNet x0_25 msmt17 | Pretrained, CPU-fast, torchreid free tier, 128-dim embedding |
| API Framework | FastAPI 0.111+ | Async-native, Pydantic v2 validation, auto Swagger docs |
| Database | PostgreSQL 16 alpine | Concurrent writes from pipeline replay, JSONB if needed, ON CONFLICT dedup |
| Cache | Redis 7 alpine | 30s metric TTL, sub-millisecond read, pub/sub for SSE |
| Dashboard | React 18 (CDN) + Recharts | No build step, SSE-native, free |
| Containerisation | Docker Compose v2 | Single-command startup, health-checked dependencies |
| Logging | structlog | JSON-structured, trace_id per request, machine-readable |

## Docker Compose Topology

The system is deployed using Docker Compose v2 for single-command startup and managed health checks. The topology includes the following services: `db` (PostgreSQL), `redis`, `api` (FastAPI), and `dashboard` (Nginx/React).

Service dependencies are strictly defined:
- The `api` service depends on `db` and `redis` being healthy (`depends_on` with health checks).
- The `dashboard` service depends on the `api` service.

Network exposure is minimized for security. The only exposed ports are `8000` for the `api` service and `3000` for the `dashboard` service. 

Data persistence is managed via volumes: `pgdata` for PostgreSQL, `redisdata` for Redis, and a bind mount `./data:/app/data` mapped as read-only for the API to process data files safely.

## Data Flow Details

### Flow 1: CCTV Frame → ENTRY Event
video frame (1080p @ 15fps)
→ YOLO11n detection (bounding boxes + confidence)
→ BoT-SORT tracking (track_id assigned)
→ OSNet embedding extraction (128-dim vector from cropped bbox)
→ VisitorGallery.resolve(track_id, embedding, timestamp)
→ cosine_similarity vs gallery (threshold 0.72)
→ if match: event_type=REENTRY, visitor_id=existing
→ if no match: event_type=ENTRY, visitor_id=new UUID
→ ZoneMapper.get_zone(bbox) → zone_id
→ StaffDetector.is_staff(frame, bbox) → bool
→ EventEmitter.emit(...) → JSONL line written to disk

### Flow 2: events.jsonl → PostgreSQL
pipeline/run.sh completes
→ POST /events/ingest with batch of up to 500 events
→ Pydantic EventBatch validation (rejects malformed, partial success)
→ For each valid event:
  INSERT INTO events (...) ON CONFLICT (event_id) DO NOTHING
→ Redis cache invalidated for affected store_ids
→ IngestResponse returned with accepted/rejected counts

### Flow 3: GET /stores/{id}/metrics
Request arrives
→ Redis GET "metrics:{store_id}"
→ HIT: return cached JSON (TTL: 30s)
→ MISS:
  → SELECT unique visitors (ENTRY, is_staff=false, today)
  → SELECT conversion via 5-min POS window join
  → SELECT avg dwell per zone
  → SELECT latest queue_depth
  → SELECT abandonment count
  → Assemble MetricsResponse
  → Redis SET "metrics:{store_id}" TTL=30s
→ Return MetricsResponse

### Flow 4: POS Correlation (Conversion Rate)
For each POS transaction (store_id, timestamp, basket_value):
Count DISTINCT visitor_ids where:
- event in (BILLING_QUEUE_JOIN or ZONE_DWELL in BILLING_ZONES)
- event.timestamp BETWEEN pos.timestamp - 300s AND pos.timestamp
- is_staff = false
→ converted_visitors / total_visitors = conversion_rate

### Flow 5: Anomaly Detection
GET /stores/{id}/anomalies triggers:

Queue spike: SELECT MAX(queue_depth) in last 5 min
→ if > QUEUE_CRITICAL_THRESHOLD(8): CRITICAL
→ if > QUEUE_WARN_THRESHOLD(5): WARN
Conversion drop: compare today_rate vs 7-day rolling avg
→ if today < avg * CONVERSION_DROP_THRESHOLD(0.70): WARN
Dead zone: for each zone in store_layout.json,
  check if any ZONE_ENTER/ZONE_DWELL in last DEAD_ZONE_MINUTES(30)
→ if absent: INFO anomaly
Stale feed: check MAX(timestamp) per store
→ if now - MAX(timestamp) > STALE_FEED_MINUTES(10): CRITICAL

## AI-Assisted Decisions

1. **Re-entry similarity threshold:** Claude suggested 0.80. Tested against sample_events.jsonl ground truth. Chosen value: 0.72 (reduces false negatives without over-matching). Override rationale: retail environments have face blur applied, so appearance embeddings rely on clothing/body shape — lower threshold needed.
2. **Anomaly thresholds:** GPT-4 suggested WARN>3, CRITICAL>5 for queue_depth. Overridden to WARN>5, CRITICAL>8 based on POS transaction frequency in pos_transactions.csv (~1 per 4 minutes) and typical retail checkout time (3–4 min). Lower thresholds produce false-positive anomalies during normal peak.
3. **POS correlation window:** AI consistently suggested 10 minutes. Chosen: 5 minutes. Rationale: the problem defines correlation as visitor in billing zone → transaction. 10-minute window causes false positives when two different customers are near billing. 5 minutes matches observed billing-to-payment latency in sample POS data.

## Known Limitations

The current architecture has several known limitations. Face blur applied to CCTV footage impacts the accuracy of Re-ID models like OSNet, making them heavily reliant on clothing and body shape embeddings, which can fail with similar attire. The pipeline operates strictly as a batch process, meaning intelligence is not strictly real-time from the camera feed but rather near real-time based on the clip ingestion frequency. Lastly, the absence of GPU acceleration for the API and subsequent components means that any future integration of heavy AI processing within the API layer will require architectural changes or strict rate limiting to prevent CPU bottlenecks.
