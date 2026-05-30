# Store Intelligence — AI-Powered Retail Analytics

Purplle Tech Challenge 2026 submission. AI-powered in-store customer
behaviour analytics using computer vision, real-time event processing,
and a live dashboard.

## Quick Start

```bash
git clone <repo>
cd store-intelligence
docker compose up -d --build
```

Wait ~30 seconds for services to start, then verify:

```bash
curl http://localhost:8000/health
```

## Accessing the System

| Service         | URL                          |
|-----------------|------------------------------|
| API (FastAPI)   | http://localhost:8000        |
| API Docs        | http://localhost:8000/docs   |
| Dashboard (live)| http://localhost:3000        |
| PostgreSQL      | localhost:5432               |
| Redis           | localhost:6379               |

## Architecture

```
┌─────────────┐    ┌─────────────┐    ┌──────────────┐    ┌────────────┐
│  Video Feed │───▶│  Pipeline   │───▶│  FastAPI API  │───▶│ Dashboard  │
│  (clips)    │    │  (YOLO+ReID)│    │  (asyncpg)   │    │ (nginx)    │
└─────────────┘    └─────────────┘    └──────┬───────┘    └────────────┘
                                             │
                                     ┌───────┴───────┐
                                     │  PostgreSQL   │
                                     │  + Redis      │
                                     └───────────────┘
```

### Services (Docker Compose)

- **db** — PostgreSQL 16 Alpine, schema auto-created via `migrations/init.sql`
- **redis** — Redis 7 Alpine, used for metrics caching (30s TTL)
- **api** — FastAPI application (multi-stage build, non-root user)
- **dashboard** — nginx Alpine serving the live analytics dashboard

## Running the Pipeline

The CV pipeline processes video clips and emits structured events:

```bash
bash pipeline/run.sh
```

This runs YOLO11n detection → BoT-SORT tracking → OSNet Re-ID →
zone mapping → event emission. Output is written to `data/events.jsonl`.

To ingest the pipeline output into the API:

```bash
curl -X POST http://localhost:8000/events/ingest \
  -H "Content-Type: application/json" \
  -d @data/events.jsonl
```

## API Endpoints

| Method | Endpoint                              | Description                    |
|--------|---------------------------------------|--------------------------------|
| GET    | `/health`                             | Service health check           |
| POST   | `/events/ingest`                      | Ingest event batch             |
| GET    | `/stores/{store_id}/metrics`          | Store KPIs                     |
| GET    | `/stores/{store_id}/funnel`           | Conversion funnel              |
| GET    | `/stores/{store_id}/heatmap`          | Zone heatmap                   |
| GET    | `/stores/{store_id}/anomalies`        | Real-time anomalies            |
| GET    | `/stores/{store_id}/metrics/stream`   | SSE live metrics stream        |

## Testing

```bash
# Run full test suite with coverage
python -m pytest tests/ --cov=app --cov-report=term-missing --cov-fail-under=70

# Current coverage: 73.86% (37 tests passing)
```

## Environment Variables

All configuration is via environment variables (no `.env` in Docker image).
See `.env.example` for defaults. Key variables:

| Variable                    | Default   | Description                        |
|-----------------------------|-----------|------------------------------------|
| `DATABASE_URL`              | —         | PostgreSQL async connection string |
| `REDIS_URL`                 | —         | Redis connection string            |
| `QUEUE_WARN_THRESHOLD`      | 5         | Queue depth warning level          |
| `QUEUE_CRITICAL_THRESHOLD`  | 8         | Queue depth critical level         |
| `STALE_FEED_MINUTES`        | 10        | Minutes before feed marked stale   |
| `METRICS_CACHE_TTL_SECONDS` | 30        | Redis cache TTL for metrics        |

## Documentation

- [Design Document](docs/DESIGN.md) — architecture, data model, API contracts
- [AI Decision Log](docs/CHOICES.md) — key technical decisions and rationale

## Live Dashboard

The dashboard is served at http://localhost:3000 via nginx. It connects to
the API's SSE endpoint for real-time metric updates and displays:

- Unique visitor count
- Conversion rate with funnel visualisation
- Zone heatmap with dwell time analysis
- Queue depth monitoring with anomaly alerts
