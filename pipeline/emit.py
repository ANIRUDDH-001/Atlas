"""
Event schema construction and JSONL writer.
Implemented fully in: 03_08_event_emitter.md
"""
import uuid
from pathlib import Path
from pipeline.types import TrackedVisitor
from pipeline.config import PipelineConfig


class EventEmitter:
    def __init__(self, output_path: Path, config: PipelineConfig):
        ...

    def emit(self, visitor: TrackedVisitor, store_id: str) -> dict:
        """Construct a StoreEvent dict and write to JSONL. Returns the dict."""
        ...

    def flush(self) -> None:
        """Flush any buffered writes to disk."""
        ...

    def close(self) -> None:
        """Close the output file handle."""
        ...
