# ATLAS

ATLAS analyzes foot traffic in physical stores. It turns recorded camera footage into visitor events and gives store operators a dashboard for traffic, dwell time, queues, and conversion when point-of-sale data is available.

## How it works

1. The Python vision pipeline detects people with YOLO, follows them with BoT-SORT, assigns zones from configured polygons, and uses appearance embeddings to help associate returning visitors.
2. The pipeline writes JSON Lines events. The FastAPI ingestion endpoint validates and stores events in PostgreSQL. Repeated event IDs are deduplicated.
3. The API computes metrics, funnels, heatmaps, and anomaly signals. Redis caches frequently requested metrics. The browser dashboard can receive updates over server-sent events.

See the [architecture notes](docs/DESIGN.md) and [Redis cache strategy](docs/cache_strategy.md).

## Run the API and dashboard

Prerequisites are Docker with Compose V2 and Python 3.11 or newer for the local scripts.

```bash
cp .env.example .env
docker compose up -d
curl http://localhost:8000/health
```

On PowerShell, use `Copy-Item .env.example .env` for the first step. Open the [dashboard](http://localhost:3000) or the [interactive API documentation](http://localhost:8000/docs). The Compose stack starts PostgreSQL, Redis, FastAPI, and an Nginx server for the dashboard. The dashboard loads its browser dependencies from CDNs.

| Endpoint | Use |
| --- | --- |
| `POST /events/ingest` | Validate and ingest a batch of detection events |
| `GET /stores/{store_id}/metrics` | Visitor counts, dwell time, queue depth, and conversion metrics |
| `GET /stores/{store_id}/funnel` | Summarize traffic across visit stages |
| `GET /stores/{store_id}/heatmap` | Inspect zone-level dwell time |
| `GET /stores/{store_id}/anomalies` | Inspect queue, conversion, and feed signals |
| `GET /stores/{store_id}/stream` | Subscribe to store updates |

## Process footage

Use footage you are authorized to process. The repository includes example camera and zone configuration. Provide video files under `data/videos/` and adapt [the camera map](pipeline/camera_map.json) and [store layout](data/store_layout.json) to your inputs. Review the default output location before running the pipeline, which replaces the previous event file.

```bash
python -m venv .venv
# Activate the environment for your shell.
python -m pip install -e ".[test]"
python run_pipeline.py
python scripts/ingest_events.py --file data/events.jsonl
```

`DATABASE_URL` and `REDIS_URL` configure the API outside Compose. `STORE_LAYOUT_PATH` and `POS_CSV_PATH` identify inputs used by the API. The [environment template](.env.example) and [Compose file](docker-compose.yml) show runtime defaults. Configure your own database credentials for any shared environment.

## Development

Run `python -m pytest tests/` with the test dependencies installed. The default tests use a local SQLite test database. The appearance embedding tests may download model weights on first use. The [Makefile](Makefile) also provides Ruff, mypy, and Docker smoke-test targets.

## Status and limitations

ATLAS is an offline video analytics prototype. Tracking, staff classification, and dwell estimates depend on camera placement, lighting, and calibration. The sample zone geometry is intentionally simple. The pipeline needs suitable model weights and video files. Conversion metrics depend on usable POS data.
