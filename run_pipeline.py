import sys
import structlog
from pathlib import Path
from pipeline.config import get_pipeline_config
from pipeline.detect import run_pipeline
import os

if __name__ == "__main__":
    structlog.configure(processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ])

    video_dir = Path("data/videos")
    layout_path = Path("data/store_layout.json")
    output_path = Path("data/events.jsonl")

    # Clear previous output
    if output_path.exists():
        os.remove(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Starting pipeline...")
    print(f"Video dir: {video_dir}")
    print(f"Layout: {layout_path}")
    print(f"Output: {output_path}")

    config = get_pipeline_config()
    total = run_pipeline(
        video_dir=video_dir,
        layout_path=layout_path,
        output_path=output_path,
        config=config,
    )
    print(f"\nPipeline complete. Total events written: {total}")
