# Atlas — Store Intelligence System

Purplle Tech Challenge 2026 — Round 2
Store: Brigade Road, Bangalore (ST1008)

## Architecture

```
CCTV Cameras (5×)
    │
    ▼
pipeline/detect.py        YOLO11n + BoT-SORT (track_buffer=90@30fps)
pipeline/tracker.py       OSNet ReID gallery (30-min re-entry window)
pipeline/staff_detector.py  HSV colour classification
pipeline/zone_mapper.py   Polygon zone attribution
    │
    ▼ events.jsonl
    │
    ▼
POST /events/ingest       FastAPI + PostgreSQL (idempotent, batched)
    │
    ├── GET /stores/{id}/metrics    unique_visitors, conversion_rate, queue_depth
    ├── GET /stores/{id}/funnel     entry → zone → billing → purchase
    ├── GET /stores/{id}/heatmap    dwell time by zone
    └── GET /stores/{id}/anomalies  queue spike, conversion drop, dead zone
    │
    ▼
dashboard/index.html      React SSE live dashboard (no build step)
```

## Quick Start

**Prerequisites:** Docker Desktop with Compose V2, Python 3.11+

```bash
# 1. Start all services (API, PostgreSQL, Redis, dashboard)
docker compose up -d

# 2. Verify health
curl http://localhost:8000/health

# 3. Run the detection pipeline
python3 run_pipeline.py --store-id STORE_ST1008

# 4. Ingest events into API
python3 scripts/ingest_events.py --file data/events.jsonl

# 5. View live metrics
curl http://localhost:8000/stores/STORE_ST1008/metrics | python3 -m json.tool

# 6. Open dashboard
open http://localhost:3000
```

## One-Command CI

```bash
make ci
```

Runs: lint → type check → pytest → docker smoke test

## Run Tests

```bash
make test
# or directly:
python3 -m pytest tests/ -v
```

## Pipeline Configuration

Key settings in `pipeline/config.py`:

| Parameter | Value | Rationale |
|---|---|---|
| `target_fps` | 30 | Camera actual fps (29.97 per camera_map.json) |
| `reid_similarity_threshold` | 0.72 | Cosine similarity for re-entry matching |
| `reid_gallery_window_sec` | 1800 | 30-minute re-entry detection window |
| `staff_hue_lower/upper` | 125/170 | Calibrated for fluorescent retail lighting |
| `staff_color_ratio_threshold` | 0.20 | Lowered for 30–60px CCTV crop distances |

BoT-SORT settings in `pipeline/botsort_retail.yaml`:

| Parameter | Value | Rationale |
|---|---|---|
| `track_buffer` | 90 | 3 seconds at 30fps — survives shelf-browse occlusion |
| `appearance_thresh` | 0.45 | Reduces ID switches between similar-looking people |

## API Reference

All endpoints at `http://localhost:8000`.

### POST /events/ingest
Batch ingest detection events. Idempotent (same `event_id` can be sent twice).
Returns partial success: `{"accepted": N, "rejected": M, "errors": [...]}`.

### GET /stores/{store_id}/metrics
Real-time store metrics. Redis-cached with 30s TTL.

```json
{
  "store_id": "STORE_ST1008",
  "unique_visitors": 86,
  "conversion_rate": 0.0,
  "avg_dwell_by_zone": [
    {"zone_id": "BILLING_QUEUE", "avg_dwell_sec": 71.2},
    {"zone_id": "WALKWAY", "avg_dwell_sec": 57.8},
    {"zone_id": "SKINCARE", "avg_dwell_sec": 46.9},
    {"zone_id": "BILLING", "avg_dwell_sec": 35.7},
    {"zone_id": "MAKEUP", "avg_dwell_sec": 33.7}
  ],
  "current_queue_depth": 6,
  "abandonment_rate": 0.1163,
  "data_confidence": "HIGH",
  "as_of": "2026-06-01T12:54:20Z"
}
```

### GET /stores/{store_id}/funnel
Visitor journey from entry to purchase.

### GET /stores/{store_id}/heatmap
Dwell time aggregated by zone.

### GET /stores/{store_id}/anomalies
Real-time anomaly detection:
- `BILLING_QUEUE_SPIKE` — queue > 5 (WARN) or > 8 (CRITICAL)
- `CONVERSION_DROP` — today's rate < 70% of 7-day average
- `DEAD_ZONE` — no zone visits in 30 minutes
- `STALE_FEED` — no events for 10 minutes

## Design Decisions

See `docs/CHOICES.md` for full decision log with AI interaction notes.
See `docs/DESIGN.md` for architecture and AI-assisted decisions section.

## Project Structure

```
pipeline/       Detection pipeline (YOLO + tracking + Re-ID)
app/            FastAPI analytics API
dashboard/      React SSE live dashboard
tests/          pytest suite
docs/           CHOICES.md, DESIGN.md, audit reports
migrations/     PostgreSQL schema
scripts/        Utility scripts (ingest, smoke test)
```

## Ground Truth Validation

Brigade Road store (10-Apr-2026):
- POS transactions: 24 invoices
- Unique buying customers: 21
- Salespersons: 5 (excluded from metrics via staff detection)
- Pipeline output: 86 unique_visitors — see `docs/PIPELINE_RUN_RESULTS.md`
