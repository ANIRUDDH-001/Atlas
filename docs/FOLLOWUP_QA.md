# Follow-Up QA Preparation

Prepared answers for the most likely contextual follow-up questions
based on the Brigade Road dataset and this system's specific implementation.

---

## Q1: "You chose YOLO11n for detection. Walk me through what you tried when it struggled with the partial occlusion cases in the billing clip."

The billing clip (CAM 5, ~2.5 min, 24.98fps) showed queue formation at the
cash counter. YOLO11n with confidence threshold 0.25 detected partially occluded
persons correctly in most frames. The key mitigation was increasing BoT-SORT's
`track_buffer` from 30 to 45 frames (3 seconds at ~25fps). Without this increase,
tracks were terminated when customers briefly stepped behind the cash counter
screen, causing the same person to generate a new ENTRY event on re-detection
1-2 seconds later. The 45-frame buffer holds the track through the occlusion window.
I validated this by checking that the number of ENTRY events from CAM_BILLING_01
was low (billing zone customers were already tracked from entry cameras, not
re-entering as new visitors).

---

## Q2: "Your visitor_id assignment uses VisitorGallery with OSNet embeddings. What breaks when a customer leaves and a different customer enters from the same direction 3 seconds later?"

The 3-second window is the critical case. With track_buffer=45 frames at ~30fps,
the track is held for 1.5 seconds after the person leaves the frame. At second 3,
the new customer gets a new track_id from BoT-SORT. The VisitorGallery checks:
has the original track exited? No - `mark_exit()` is only called when the
DirectionDetector confirms an outbound crossing at the entry threshold. If the
original visitor hasn't crossed the exit line yet (still inside the store), their
gallery entry has `exit_time=None` and is excluded from re-entry matching. The new
customer's embedding is compared only against entries with `exit_time` set. So the
two customers will correctly get different visitor_ids. The edge case where this
breaks: if the original visitor exits at second 2 (mark_exit sets exit_time) and
the new customer enters at second 3 wearing very similar clothing, the 1-second
gap may yield a false REENTRY. Mitigation: the 3-second minimum time gap makes
this scenario very rare in practice at retail walking speeds.

---

## Q3: "Your /funnel endpoint is accurate for the test clips. At 40 live stores sending events in real time, what is the first thing that breaks?"

The PostgreSQL CTE in `/funnel` uses a full GROUP BY on visitor_id across today's
events - this is a full table scan filtered by store_id and date. At 40 stores
with real-time streaming, this runs thousands of times per minute. The first
bottleneck is the `idx_events_store_time` index scan: at high volume, the CTE
materialises millions of rows before grouping. The fix: (1) a materialized view
for daily session summaries, rebuilt on each ingest batch via `REFRESH MATERIALIZED
VIEW CONCURRENTLY`; (2) partition the events table by date using PostgreSQL
declarative partitioning so the planner can prune old partitions automatically.
The Redis cache (30s TTL) already addresses read spikes - the bottleneck is the
write path's impact on read query planning.

---

## Q4: "In CHOICES.md you considered TimescaleDB but chose PostgreSQL + Redis. What would make you change that decision?"

Three conditions would trigger the switch: (1) Event volume exceeds 10,000 events
per minute across all stores - at that volume, PostgreSQL's B-tree index on
(store_id, timestamp) starts showing write amplification and the time-series
compression in TimescaleDB would reduce storage by 60-80%. (2) The anomaly
detection queries need sub-second freshness - TimescaleDB's continuous aggregates
materialise in the background with <1s lag, removing the need for the Redis
cache layer entirely. (3) Historical trend analysis is required beyond 7 days -
TimescaleDB's columnar storage with compression makes 30/60/90-day queries
orders of magnitude faster than vanilla PostgreSQL on wide time windows.
For the Brigade Road dataset (24 transactions in 9.5 hours), none of these
thresholds are approached - PostgreSQL + Redis is the correct choice at this scale.
