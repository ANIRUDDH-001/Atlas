import cv2
import numpy as np
from pathlib import Path

def sample_upper_body_hsv(video_path: Path, sample_frames: list[int]):
    cap = cv2.VideoCapture(str(video_path))
    s_samples = []
    v_samples = []

    for frame_idx in sample_frames:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            continue

        h, w = frame.shape[:2]
        # Same logic as _extract_upper_body
        upper_region = frame[h//4:h//2, w//4:3*w//4]
        hsv = cv2.cvtColor(upper_region, cv2.COLOR_BGR2HSV)
        
        s_samples.append(hsv[:,:,1].mean())
        v_samples.append(hsv[:,:,2].mean())

    cap.release()
    return s_samples, v_samples

s_samples, v_samples = sample_upper_body_hsv(
    Path("data/videos/STORE_ST1008/CAM 5.mp4"),
    sample_frames=[100, 200, 300, 500, 700]
)

print(f"Mean Saturation: {np.mean(s_samples):.1f}")
print(f"Mean Value: {np.mean(v_samples):.1f}")
