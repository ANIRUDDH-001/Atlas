# Redis Cache Strategy

## Keys and TTLs
| Key Pattern | TTL | Invalidated When |
|---|---|---|
| `metrics:{store_id}` | 30s | POST /events/ingest for that store |
| `ratelimit:ingest:{ip}` | 60s | Auto-expires (sliding window) |

## Cache-Aside Pattern
All read endpoints use cache-aside:
1. Check Redis for key
2. Cache HIT: return cached value immediately
3. Cache MISS: compute from DB, store in Redis with TTL, return value

## Fail-Open Policy
Redis failures are non-fatal:
- Cache read failure → falls through to DB query
- Cache write failure → logged as warning, request succeeds
- Cache delete (invalidation) failure → logged as warning, data becomes stale
  for up to TTL duration (max 30s)

## Why 30s TTL
POS transactions arrive ~every 4 minutes. A 30s cache is fresh enough
for operational use while reducing DB load during high-traffic periods.
