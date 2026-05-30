"""
Polygon-based zone classification using store_layout.json.
Implemented fully in: 03_07_zone_mapper.md
"""
from pathlib import Path
from pipeline.types import StoreLayout, ZoneDefinition
from pipeline.config import PipelineConfig


class ZoneMapper:
    def __init__(self, layout: StoreLayout, camera_id: str, config: PipelineConfig):
        ...

    def get_zone(self, bbox: tuple) -> str | None:
        """Return zone_id if bbox centroid falls in a zone polygon, else None."""
        ...

    @staticmethod
    def load_layout(store_layout_path: Path, store_id: str) -> StoreLayout:
        """Parse store_layout.json and return StoreLayout for store_id."""
        ...
