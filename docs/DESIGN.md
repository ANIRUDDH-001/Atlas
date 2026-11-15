# ATLAS architecture

The batch vision pipeline is separate from the analytics API. This lets the API ingest recorded detection events without decoding footage in the request path.

- [Vision pipeline](../pipeline/detect.py) detects and tracks people, associates tracks with configured zones, and writes an event stream.
- [Ingestion](../app/ingestion.py) validates events and inserts them in batches. The [database schema](../migrations/init.sql) makes the event ID unique.
- [Metrics and cache](../app/metrics.py) expose per-store aggregates. [Cache behavior](cache_strategy.md) describes expiry and the fallback when Redis is unavailable.
- [Dashboard](../dashboard/index.html) loads aggregate data and subscribes to the API's server-sent event stream.

Camera IDs and zone polygons should be configured for each input. Appearance matching and staff colour inference are heuristics. Point-of-sale records are separate inputs used to estimate conversion.
