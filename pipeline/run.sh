#!/usr/bin/env bash
set -euo pipefail

# ── Store Intelligence Pipeline Runner ────────────────────────────────────────
# Usage: bash pipeline/run.sh
# Output: data/events.jsonl
#
# Environment overrides:
#   VIDEO_DIR           (default: ./data/videos)
#   STORE_LAYOUT_PATH   (default: ./data/store_layout.json)
#   PIPELINE_OUTPUT_PATH (default: ./data/events.jsonl)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

VIDEO_DIR="${VIDEO_DIR:-./data/videos}"
LAYOUT_PATH="${STORE_LAYOUT_PATH:-./data/store_layout.json}"
OUTPUT_PATH="${PIPELINE_OUTPUT_PATH:-./data/events.jsonl}"

echo "=========================================="
echo "  Store Intelligence Pipeline"
echo "  Video dir:   $VIDEO_DIR"
echo "  Layout:      $LAYOUT_PATH"
echo "  Output:      $OUTPUT_PATH"
echo "=========================================="

# Validate prerequisites
if [ ! -d "$VIDEO_DIR" ]; then
  echo "ERROR: Video directory not found: $VIDEO_DIR"
  echo "Expected structure: $VIDEO_DIR/{store_id}/{camera_id}.mp4"
  exit 1
fi

if [ ! -f "$LAYOUT_PATH" ]; then
  echo "ERROR: store_layout.json not found: $LAYOUT_PATH"
  exit 1
fi

# Clear previous output
if [ -f "$OUTPUT_PATH" ]; then
  echo "Clearing previous output: $OUTPUT_PATH"
  rm -f "$OUTPUT_PATH"
fi

mkdir -p "$(dirname "$OUTPUT_PATH")"

# Run pipeline
python3 - <<PYEOF
import sys, structlog
from pathlib import Path
from pipeline.config import get_pipeline_config
from pipeline.detect import run_pipeline

structlog.configure(processors=[
    structlog.processors.TimeStamper(fmt="iso"),
    structlog.stdlib.add_log_level,
    structlog.dev.ConsoleRenderer(),
])

config = get_pipeline_config()
total = run_pipeline(
    video_dir=Path("$VIDEO_DIR"),
    layout_path=Path("$LAYOUT_PATH"),
    output_path=Path("$OUTPUT_PATH"),
    config=config,
)
print(f"Pipeline complete. Total events written: {total}")
print(f"Output: $OUTPUT_PATH")
PYEOF

echo ""
echo "Pipeline finished. Verifying output..."
if [ -f "$OUTPUT_PATH" ]; then
  LINE_COUNT=$(wc -l < "$OUTPUT_PATH")
  echo "Events written: $LINE_COUNT"
  echo "First event:"
  head -1 "$OUTPUT_PATH" | python3 -m json.tool
else
  echo "ERROR: Output file not created"
  exit 1
fi
