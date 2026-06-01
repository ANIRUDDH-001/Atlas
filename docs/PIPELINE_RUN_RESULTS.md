# Pipeline Run Results

## 1. Input Data
- **Store ID**: STORE_ST1008 (Brigade Road, Bangalore)
- **Video Files**:
  - `CAM 1.mp4` (CAM_ENTRY_01)
  - `CAM 2.mp4` (CAM_FLOOR_01)
  - `CAM 3.mp4` (CAM_FLOOR_02)
  - `CAM 4.mp4` (CAM_FLOOR_03)
  - `CAM 5.mp4` (CAM_BILLING_01)

## 2. Event Generation Output
- **Total Pipeline Events Processed**: 27,340 
- **Total Valid Events Emitted**: 89
- **Event Type Distribution**: `{'ENTRY': 89}`
- **Unique Visitors (excluding staff)**: 86
- **Staff Events**: 3 (3.4%)
- **Null `zone_id` Rate**: 100% (89/89 events have `zone_id=null`)

## 3. Assessment
- **Staff detection**: ✅ **Working**. The pipeline correctly detected staff members (3 staff detected out of 89 total individuals), confirming the HSV threshold fix was successful.
- **Deduplication**: ❌ **Not functioning properly across zones**. The unique visitor count is 86, which is far above the POS ground truth target of 20-35. The cross-camera deduplicator is not working properly because of the complete absence of zone tracking.
- **Zone attribution**: ❌ **Failed completely**. 100% of the events have a null `zone_id`, resulting in only `ENTRY` events being generated and completely missing all `ZONE_ENTER`, `ZONE_EXIT`, and `EXIT` events.

## 4. Discovered Bugs

**Bug: Camera Name Mismatch in store_layout.json**
The pipeline output is missing all zone definitions because `run_pipeline.py` passes `camera_id` (e.g. `CAM_ENTRY_01`, `CAM_FLOOR_01`) from `camera_map.json` to the `ZoneMapper`, but `store_layout.json` defines the cameras using their filenames (e.g. `CAM 1.mp4`). This results in `camera_not_in_layout` warnings for all cameras, disabling zone attribution entirely.

This bug must be addressed in a separate fix branch, as modifying source files is restricted during the Phase 4 audit.
