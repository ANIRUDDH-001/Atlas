# Handoff: CV Pipeline → UI/UX Dashboard

## What the Dashboard Receives
The SSE stream at `GET /stores/{store_id}/metrics/stream` emits
`MetricsResponse` JSON every 5 seconds.

The anomalies polling endpoint `GET /stores/{store_id}/anomalies` returns
`AnomaliesResponse` JSON.

## SSE Event Format
```
data: {"store_id":"STORE_BLR_002","unique_visitors":47,"conversion_rate":0.2340,...}\n\n
```

## MetricsResponse Fields Available to Dashboard
- `store_id`: string
- `unique_visitors`: integer (0 if no visitors)
- `conversion_rate`: float or null
- `avg_dwell_by_zone`: [{zone_id, avg_dwell_sec}]
- `current_queue_depth`: integer
- `abandonment_rate`: float or null
- `data_confidence`: "HIGH" or "LOW"
- `as_of`: ISO-8601 datetime string

## AnomalyRecord Fields Available to Dashboard
- `anomaly_id`: one of BILLING_QUEUE_SPIKE / CONVERSION_DROP / DEAD_ZONE / STALE_FEED
- `severity`: INFO / WARN / CRITICAL
- `suggested_action`: human-readable string (show in alert)
- `detected_at`: ISO-8601 datetime

## Dashboard Requirements from Problem Spec
- At least one metric updating in real time (SSE stream)
- Web UI preferred over terminal (higher score)
- Served at http://localhost:3000
- Must show anomaly alerts with severity colouring

## API Base URL
- Local dev: http://localhost:8000
- Docker Compose: http://api:8000 (internal) / http://localhost:8000 (host)

## CORS
API allows: http://localhost:3000
