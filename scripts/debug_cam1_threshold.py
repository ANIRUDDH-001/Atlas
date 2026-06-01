import cv2
from pathlib import Path
from ultralytics import YOLO
import json

print("Loading YOLO11n...")
model = YOLO("yolo11n.pt")
input_dir = Path(r"data\videos\STORE_ST1008")
output_dir = Path(r"dashboard\annotated")
output_dir.mkdir(parents=True, exist_ok=True)

video_path = input_dir / "CAM 1.mp4"
out_path = output_dir / "CAM_1_ENTRY_DEBUG.webm"

print(f"\n--- Starting {video_path.name} ---")

cap = cv2.VideoCapture(str(video_path))
fps = int(cap.get(cv2.CAP_PROP_FPS) or 25)
width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1920)
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 1080)
cap.release()

out = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*'vp80'), fps, (width, height))

layout_file = Path("data/store_layout.json")
layout_data = json.loads(layout_file.read_text())
threshold_y = layout_data["STORE_ST1008"]["cameras"]["CAM_ENTRY_01"]["threshold_y"]
threshold_py = int(threshold_y * height)

frame_count = 0
max_frames = fps * 30 

for result in model.track(source=str(video_path), stream=True, persist=True, tracker="pipeline/botsort_retail.yaml", classes=[0], conf=0.32, verbose=False):
    annotated_frame = result.plot()
    
    # Draw threshold line
    cv2.line(annotated_frame, (0, threshold_py), (width, threshold_py), (0, 0, 255), 3)
    cv2.putText(annotated_frame, f"Threshold Y: {threshold_y} ({threshold_py}px)", (50, threshold_py - 10), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
    
    # Draw foot points
    if result.boxes is not None and result.boxes.id is not None:
        for box, track_id in zip(result.boxes.xyxy, result.boxes.id):
            x1, y1, x2, y2 = map(int, box[:4])
            foot_y = y2
            cx = (x1 + x2) // 2
            cv2.circle(annotated_frame, (cx, foot_y), 5, (0, 255, 0), -1)
            cv2.putText(annotated_frame, f"Foot: {foot_y/height:.2f}", (cx, foot_y + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
    out.write(annotated_frame)
    frame_count += 1
    if frame_count % 150 == 0:
        print(f"{video_path.name}: Processed {frame_count} frames...")
    if frame_count >= max_frames:
        break

out.release()
print(f"Saved {out_path}")
