from ultralytics import YOLO
model = YOLO("yolo11n.pt")
import yaml
cfg = yaml.safe_load(open("pipeline/botsort_retail.yaml"))
print(f"PASS: Tracker config loaded, with_reid={cfg['with_reid']}")
