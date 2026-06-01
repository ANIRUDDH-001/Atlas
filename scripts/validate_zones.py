import cv2
import json
import numpy as np
from pathlib import Path

def draw_zones(frame, zones: dict, alpha=0.3):
    overlay = frame.copy()
    colours = [(0,255,0),(255,0,0),(0,0,255),(255,255,0),(0,255,255)]
    for i, (zone_id, polygon) in enumerate(zones.items()):
        h, w = frame.shape[:2]
        pts = np.array([[int(x*w), int(y*h)] for x,y in polygon], dtype=np.int32)
        cv2.fillPoly(overlay, [pts], colours[i % len(colours)])
        cx, cy = pts.mean(axis=0).astype(int)
        cv2.putText(overlay, zone_id, (cx-20, cy),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1)
    return cv2.addWeighted(frame, 1-alpha, overlay, alpha, 0)

layout = json.load(open("data/store_layout.json"))
cameras = layout.get("STORE_ST1008", {}).get("cameras", {})

for camera_id, cam_cfg in cameras.items():
    zones = cam_cfg.get("zones", {})
    if not zones:
        continue
    source = f"data/videos/STORE_ST1008/{cam_cfg['source_file']}"
    cap = cv2.VideoCapture(source)
    cap.set(cv2.CAP_PROP_POS_FRAMES, 100)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        continue
    annotated = draw_zones(frame, zones)
    out_path = f"data/zone_validation_{camera_id}.jpg"
    cv2.imwrite(out_path, annotated)
    print(f"Saved zone overlay: {out_path}")
