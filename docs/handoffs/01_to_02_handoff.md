# Handoff: Architecture → Backend Engineering

## What Was Decided
- Framework: FastAPI 0.111+ with asyncpg
- DB: PostgreSQL 16, schema in `migrations/init.sql` (to be written in phase 06)
- Cache: Redis 7, client in `app/cache.py`
- Event schema: `app/models.py` — `StoreEvent`, `EventBatch`
- Response models: all 8 in `app/models.py`
- Config: `app/config.py` via `get_settings()`
- Exceptions: `app/exceptions.py`
- Constants: `app/constants.py`

## What You Must Not Change
- Event schema field names or types
- Endpoint paths (exactly as in 01_03)
- MAX_INGEST_BATCH_SIZE = 500
- POS_CORRELATION_WINDOW_SECONDS = 300

## Endpoint Implementation Order (dependency order)
1. `app/health.py` — no DB dependency, implement first for acceptance gate
2. `app/ingestion.py` — write path, must work before reads
3. `app/metrics.py` — depends on ingestion
4. `app/funnel.py` — depends on sessions (same table as metrics)
5. `app/heatmap.py` — depends on zone events
6. `app/anomalies.py` — depends on all other endpoints' queries

## Database Table Dependencies
- `events` table: all endpoints read from here
- `pos_transactions` table: metrics and funnel endpoints join to this
- Both tables defined in `migrations/init.sql` (Phase 06)

## Critical Implementation Rules
1. All DB calls must use async SQLAlchemy (`async with session:`)
2. Staff events (`is_staff=true`) MUST be excluded from all customer metrics
3. Re-entry events: `visitor_id` deduplication in funnel — count by DISTINCT visitor_id not by event count
4. Idempotency: `ON CONFLICT (event_id) DO NOTHING` on every INSERT
5. Zero-traffic stores must return 0 (not null) for counts, null for rates
6. No raw stack traces in HTTP responses (use app/exceptions.py handlers)

## Files to Implement
- `app/main.py`
- `app/ingestion.py`
- `app/metrics.py`
- `app/funnel.py`
- `app/heatmap.py`
- `app/anomalies.py`
- `app/health.py`
- `app/pos_loader.py` (new — for loading pos_transactions.csv at startup)
