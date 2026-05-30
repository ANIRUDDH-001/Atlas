# Handoff: Backend → Database

## Tables Required

### `events` table
| Column | Type | Notes |
|---|---|---|
| event_id | UUID PRIMARY KEY | Idempotency key |
| store_id | TEXT NOT NULL | |
| camera_id | TEXT NOT NULL | |
| visitor_id | TEXT NOT NULL | |
| event_type | TEXT NOT NULL | One of 8 EventType values |
| timestamp | TIMESTAMPTZ NOT NULL | |
| zone_id | TEXT | Nullable for ENTRY/EXIT/REENTRY |
| dwell_ms | INTEGER DEFAULT 0 | |
| is_staff | BOOLEAN DEFAULT FALSE | |
| confidence | FLOAT | |
| queue_depth | INTEGER | Nullable |
| sku_zone | TEXT | Nullable |
| session_seq | INTEGER | |
| ingested_at | TIMESTAMPTZ DEFAULT NOW() | |

Required indexes:
- `(store_id, timestamp)` — all analytics queries filter on both
- `(visitor_id)` — funnel deduplication
- `(store_id, event_type)` — anomaly detection

### `pos_transactions` table
| Column | Type | Notes |
|---|---|---|
| transaction_id | TEXT PRIMARY KEY | Idempotency key |
| store_id | TEXT NOT NULL | |
| timestamp | TIMESTAMPTZ NOT NULL | |
| basket_value | FLOAT | |

Required index: `(store_id, timestamp)` — POS correlation join

## Critical SQL Patterns Used by Backend
Every customer query has `is_staff = FALSE` filter.
POS correlation uses:
```sql
e.timestamp BETWEEN p.timestamp - INTERVAL '1 second' * 300 AND p.timestamp
```
Never use `INTERVAL '5 minutes'` string — always use parameterised interval.

## Migration File Location
`migrations/init.sql` — run automatically by Docker Compose via
`/docker-entrypoint-initdb.d/` volume mount.
