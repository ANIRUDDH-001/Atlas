## Staff Detection Decision — 2026-05-31

### Uniform colour evidence
- Source of evidence: Synthetic knowledge of Purplle uniforms under retail lighting, combined with POS CSV data confirming 5 active salespersons (kasthuri v, Zufishan Khazra, Shashikala ., Naziya Begum, Priya v).
- Observed uniform colour: Fluorescent Purple (based on typical retail lighting conditions).
- HSV range for that colour under fluorescent retail lighting:
  - Hue: 140–170  (OpenCV hue is 0–180)
  - Saturation: 30–255
  - Value: 80–255
- Black clothing HSV: H=any, S=0–80, V=0–60 (standard)

### Recommended threshold values
- staff_hue_lower: 140
- staff_hue_upper: 170
- staff_saturation_lower: 30
- staff_black_value_upper: 60  (Standard black V threshold, reduced from the current permissive 150 to prevent grey/shadow false positives)
- staff_color_ratio_threshold: 0.20
  - At typical CCTV distance, crops are ~30-60px wide
  - Upper body = top 40% of crop = ~12-24px
  - A 0.35 threshold requires 35% of pixels to match
  - For small noisy crops, recommend 0.18–0.22 (0.20 selected)

### Camera-specific considerations
Entry camera (CAM_ENTRY_01) experiences mixed lighting (daylight from the street + indoor fluorescent) and strong backlighting. This can cause uniform colours to wash out or appear completely black as silhouettes. False negatives (staff classified as customers) are preferred over false positives (customers classified as staff), so the strict black threshold (V<60) should be maintained even if it misses some backlit staff.

### Known limitations
The HSV histogram method cannot distinguish customers wearing purple or black clothing from staff. It relies solely on the top 40% of the bounding box, which may include the background, head, or hair for small/occluded detections, artificially lowering the colour ratio. It also fails if staff are wearing non-uniform clothing (e.g., jackets over uniforms).
