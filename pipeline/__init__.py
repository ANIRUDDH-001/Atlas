"""
Store Intelligence — CCTV Detection Pipeline

Processes raw video clips to produce structured StoreEvent JSONL output.
Run via: bash pipeline/run.sh

Pipeline stages:
1. detect.py     — YOLO11n person detection + BoT-SORT tracking
2. tracker.py    — Visitor gallery + Re-ID + re-entry detection
3. zone_mapper.py — Polygon zone classification from store_layout.json
4. staff_detector.py — HSV-based staff uniform classification
5. emit.py       — Event schema construction + JSONL writer
"""
