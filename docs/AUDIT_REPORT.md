## ATLAS SYSTEM AUDIT — 2026-05-31 14:38:00 IST

### 1. store_layout.json status
- EXISTS
- Cameras present: CAM_ENTRY_01, CAM_FLOOR_01, CAM_FLOOR_02, CAM_FLOOR_03, CAM_BILLING_01
- Zone names per camera:
  | Camera | Zones |
  |--------|-------|
  | CAM_ENTRY_01 | *None (threshold_y only)* |
  | CAM_FLOOR_01 | SKINCARE, HAIRCARE, WALKWAY |
  | CAM_FLOOR_02 | MAKEUP, FRAGRANCE, WALKWAY |
  | CAM_FLOOR_03 | BEAUTY, WELLNESS, WALKWAY |
  | CAM_BILLING_01 | BILLING, BILLING_QUEUE |
- Zone name match with BILLING_ZONES: PARTIAL
  - Matched: BILLING
  - Unmatched: CHECKOUT, CASH_COUNTER

### 2. FPS mismatch
- camera_map.json actual fps: 
  - CAM_ENTRY_01, CAM_FLOOR_01, CAM_FLOOR_02: 29.97
  - CAM_FLOOR_03, CAM_BILLING_01: 24.98
- config.py target_fps: 15
- botsort_retail.yaml track_buffer: 45
- Effective track duration at actual fps:
  - 29.97 fps cameras: 45 / 29.97 = 1.50 seconds
  - 24.98 fps cameras: 45 / 24.98 = 1.80 seconds
- Intended duration: 3.0 seconds (45 frames / 15 target_fps)

### 3. Root cause chain (Bug 1 — visitor inflation)
- frame_crop extraction frequency: Every 15 frames
- % of detections with None embedding: ~93.3% (14 out of 15 frames)
- _find_best_match behaviour with None: Immediately returns `None, 0.0`
- Consequence: When a person's track drops and is re-acquired by BoT-SORT as a new track ID, `VisitorGallery` attempts to resolve re-entry. However, because `frame_crop` is `None` for 93.3% of the frames, no embedding is extracted. `_find_best_match` returns no match, and a brand new `visitor_id` (ENTRY event) is incorrectly generated. This leads to massive unique visitor inflation.

### 4. Staff detection status
- Calls per 100 detections: ~6.67 (called once every 15 frames)
- HSV hue range: 130–160
- Saturation floor: 50
- Threshold: 0.35
- Assessment: NO, it will not correctly exclude staff. `is_staff` defaults to `False` on every detection. It is only set to `True` on the exact frame where a `frame_crop` is processed. For the other 14 out of 15 frames, the staff member emits events as a customer (`is_staff = False`), severely contaminating the customer metrics.

### 5. Dead code found
- DIRECTION_HISTORY: Located in `pipeline/detect.py` (line 34). Declared as a global variable but never updated, as it is shadowed by a local `direction_history` dictionary created within `Detector.process_clip` (line 104).
- Detector.get_direction(): Located in `pipeline/detect.py` (line 236). Reads from the empty global `DIRECTION_HISTORY` (hence always returns `None`) and is completely unreferenced by the rest of the codebase (the pipeline uses `DirectionDetector` in `pipeline/direction.py` instead).

### 6. API issues found
- queue_depth date filter: MISSING. In `app/metrics.py` (line 124), the query uses `ORDER BY timestamp DESC LIMIT 1` but fails to filter by `DATE(timestamp) = CURRENT_DATE`. It will incorrectly surface stale queue depths from prior days.
- data_confidence threshold: Value is 20 unique visitors. Assessment: The threshold is correct and queries `ENTRY` events, but the implementation is redundant (re-calculating total sessions separately in `heatmap.py` while reusing existing `unique_visitors` in `metrics.py`).
- POS zone name match: PARTIAL status. `BILLING` maps correctly, but the POS constraints don't include `BILLING_QUEUE`, and the constants look for `CHECKOUT` and `CASH_COUNTER` which don't exist in the layout.

### 7. Test coverage gaps
- `VisitorGallery`: No test asserting correct re-entry behavior when `embedding` is `None` (which triggers the inflation bug).
- `StaffDetector`: No test validating that `is_staff` state persists across frames where `frame_crop` is missing.
- `app/metrics.py`: No test asserting that `queue_depth` ignores previous days' data (verifying the missing date filter).
- `app/funnel.py`: No tests validating the intersection between `BILLING` zones and POS transactions window.
- `CrossCameraDeduplicator`: No tests handling `None` embeddings.

### 8. Current live metrics
- unique_visitors: Unreachable (Docker API connection failed locally).
- event counts by type: Unreachable (Docker API connection failed locally).
- is_staff events: Unreachable (Docker API connection failed locally).

### 9. Phase execution order
1. **Pipeline Core Fixes (FPS & Dead Code)**: Fix `botsort_retail.yaml` / `config.py` FPS handling and remove the dead code in `detect.py`. This stabilizes the tracker buffer.
2. **State Persistence (Staff & Embeddings)**: Modify `VisitorGallery` and `detect.py` to persist `is_staff` classification and recent embeddings across the 14 frames where crops are omitted. This fixes the massive visitor inflation and staff contamination bugs.
3. **API & Logic Alignment**: Fix `app/metrics.py` to include the missing date filter for `queue_depth`, and align `app/constants.py` `BILLING_ZONES` with `store_layout.json`.
4. **Testing**: Add missing test scenarios to `tests/test_pipeline.py` and `tests/test_metrics.py` to prevent regressions.
5. **Data Regeneration**: After fixes, the pipeline must be rerun to generate a clean, correct `events.jsonl` file so the live metrics will reflect accurate data.
