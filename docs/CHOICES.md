# Decision 1: Detection Model and Tracker Configuration

Modified BoT-SORT defaults: increased track_buffer from 30 to 45 frames
(3 seconds at 15fps) to handle partial occlusion behind retail displays.
Enabled with_reid=True because retail density causes frequent crossing
paths. Increased proximity_thresh to 0.6 to account for face blur
reducing appearance embedding quality.

Chose OSNet x0.25 (MSMT17) for Re-ID. AI suggested larger OSNet x1.0
for better accuracy. Overrode to x0.25 because: (1) faces are blurred —
larger models don't recover meaningful face features; (2) x0.25 runs at
~50ms/crop on CPU vs ~180ms for x1.0; (3) MSMT17 pretraining covers
indoor pedestrian scenarios similar to retail environments.

Staff detection via HSV upper-body colour histogram. AI suggested training
a binary classifier. Overrode because no labelled staff/customer training
data was available in the dataset. HSV hue is lighting-invariant — the
problem spec notes 'natural light, fluorescent, mixed' conditions, making
HSV more robust than RGB thresholds. Conservative threshold (0.25) means
we prefer calling a staff member a customer rather than excluding real
customers — false positives hurt conversion_rate accuracy.

# Decision 2: Database Engine — PostgreSQL over SQLite

AI initially scaffolded the prototype on SQLite for speed. Overrode to
PostgreSQL because: (1) the Docker Compose acceptance gate requires a
multi-service architecture, and PostgreSQL runs as its own container with
proper isolation; (2) PostgreSQL supports `BOOL_OR`, `FILTER`, and
`INTERVAL` natively — SQLite requires cumbersome workarounds; (3) the
`asyncpg` driver provides true async I/O, while `aiosqlite` serialises
all writes behind a single thread lock; (4) PostgreSQL's MVCC handles
concurrent ingestion and read queries without blocking, which matters
when the dashboard is polling metrics every 5 seconds while the pipeline
is writing hundreds of events per batch.

# Decision 3: Caching Strategy — Redis with Short TTL

Chose Redis with a 30-second TTL for metrics caching. AI suggested an
in-memory LRU cache to avoid the Redis dependency. Overrode because:
(1) the acceptance gate already requires Redis in the Docker Compose
stack; (2) Redis cache survives API restarts — important during rolling
deployments; (3) a 30-second TTL balances freshness against database
load — the dashboard polls every 5 seconds, meaning 5 out of 6 requests
are served from cache; (4) Redis provides atomic operations for future
rate limiting and session storage needs.

# Decision 4: Session Definition — Visitor-Day Grain

A session is defined as a unique `(visitor_id, store_id, DATE(timestamp))`
tuple. Re-entry events (event_type=REENTRY) do NOT create new sessions —
they map back to the same visitor_id. AI suggested a time-gap-based
session definition (30 minutes of inactivity = new session). Overrode
because: (1) the problem spec explicitly defines re-entry as the same
visitor returning, not a new session; (2) visitor-day grain simplifies
funnel analysis — each visitor has exactly one funnel path per day;
(3) time-gap sessions would double-count visitors who step outside for
a phone call and return, inflating unique_visitors and deflating
conversion_rate.

# Decision 5: Input Validation — Regex over Schema-Only

Added `STORE_ID_REGEX = r'^STORE_[A-Z]{2,5}_\d{3}$'` validation at the
path parameter level. AI relied solely on Pydantic model validation.
Overrode because: (1) path traversal attacks like `../../etc/passwd`
bypass Pydantic since store_id arrives as a path parameter, not a body
field; (2) early rejection at the middleware layer avoids database round
trips for clearly invalid input; (3) the regex matches the problem spec's
`STORE_<CITY>_<NUM>` format exactly, serving as both security and
documentation.
