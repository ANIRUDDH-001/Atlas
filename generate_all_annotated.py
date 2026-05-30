import cv2
from pathlib import Path
from ultralytics import YOLO

print("Loading YOLO11n...")
model = YOLO("yolo11n.pt")
input_dir = Path(r"data\videos\STORE_ST1008")
output_dir = Path(r"dashboard\annotated")
output_dir.mkdir(parents=True, exist_ok=True)

# Process all 5 cameras sequentially
for i in range(1, 6):
    video_path = input_dir / f"CAM {i}.mp4"
    if not video_path.exists():
        continue
        
    out_path = output_dir / f"CAM_{i}.webm"
    print(f"\n--- Starting {video_path.name} ---")
    
    cap = cv2.VideoCapture(str(video_path))
    fps = int(cap.get(cv2.CAP_PROP_FPS) or 25)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1920)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 1080)
    cap.release()
    
    out = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*'vp80'), fps, (width, height))
    
    frame_count = 0
    # Limiting to 30 seconds per video so your laptop doesn't melt, 
    # but still gives a massive chunk of annotated footage!
    max_frames = fps * 30 
    
    try:
        for result in model.track(source=str(video_path), stream=True, persist=True, tracker="pipeline/botsort_retail.yaml", classes=[0], conf=0.25, verbose=False):
            annotated_frame = result.plot()
            out.write(annotated_frame)
            frame_count += 1
            if frame_count % 150 == 0:
                print(f"{video_path.name}: Processed {frame_count} frames...")
            if frame_count >= max_frames:
                break
    finally:
        out.release()
        print(f"Saved {out_path}")

print("\nALL VIDEOS COMPLETED.")
