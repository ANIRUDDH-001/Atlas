"""
Polygon-based zone classification from store_layout.json.

Maps bounding box positions to named store zones using point-in-polygon
tests. Polygon coordinates are normalised 0.0–1.0 relative to frame size.

Zone attribution uses the bottom-centre of the bounding box (foot position)
rather than the geometric centroid — foot position more accurately reflects
where in the store the person is physically standing.
"""
import json
import structlog
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from shapely.geometry import Point, Polygon as ShapelyPolygon

from pipeline.config import PipelineConfig

logger = structlog.get_logger()


@dataclass
class CameraZones:
    """Parsed zone definitions for one camera."""
    camera_id: str
    camera_type: str           # "entry_exit" or "floor" or "billing"
    threshold_y: Optional[float]  # For entry_exit cameras
    zones: dict[str, ShapelyPolygon]  # zone_id → shapely Polygon


class ZoneMapper:
    """
    Maps bounding box foot positions to named store zones.

    Usage:
        mapper = ZoneMapper.from_layout_file(layout_path, store_id, camera_id, config)
        zone_id = mapper.get_zone(bbox, frame_shape)
    """

    def __init__(
        self,
        camera_zones: CameraZones,
        config: PipelineConfig,
    ):
        self._camera_zones = camera_zones
        self._config = config

    @classmethod
    def from_layout_file(
        cls,
        layout_path: Path,
        store_id: str,
        camera_id: str,
        config: PipelineConfig,
    ) -> "ZoneMapper":
        """
        Factory method: parse store_layout.json and return a ZoneMapper
        for the specified store + camera combination.

        Raises:
            FileNotFoundError: if layout_path does not exist
            KeyError: if store_id or camera_id not in layout
            ValueError: if polygon has fewer than 3 points
        """
        if not layout_path.exists():
            raise FileNotFoundError(f"store_layout.json not found: {layout_path}")

        raw = json.loads(layout_path.read_text())

        if store_id not in raw:
            raise KeyError(f"store_id '{store_id}' not in store_layout.json")

        store = raw[store_id]
        cameras = store.get("cameras", {})

        if camera_id not in cameras:
            # Camera not in layout — return a no-op mapper
            logger.warning("camera_not_in_layout",
                          store_id=store_id, camera_id=camera_id)
            camera_zones = CameraZones(
                camera_id=camera_id,
                camera_type="unknown",
                threshold_y=0.5,
                zones={},
            )
            return cls(camera_zones, config)

        cam_cfg = cameras[camera_id]
        cam_type = cam_cfg.get("type", "floor")
        threshold_y = cam_cfg.get("threshold_y")

        zones: dict[str, ShapelyPolygon] = {}
        raw_zones = cam_cfg.get("zones", {})

        for zone_id, points in raw_zones.items():
            if len(points) < 3:
                raise ValueError(
                    f"Zone '{zone_id}' has fewer than 3 polygon points"
                )
            zones[zone_id] = ShapelyPolygon(points)

        camera_zones = CameraZones(
            camera_id=camera_id,
            camera_type=cam_type,
            threshold_y=threshold_y,
            zones=zones,
        )

        logger.info("zone_mapper_initialized",
                    store_id=store_id,
                    camera_id=camera_id,
                    zone_count=len(zones),
                    zones=list(zones.keys()))

        return cls(camera_zones, config)

    def get_zone(
        self,
        bbox: tuple,
        frame_shape: tuple,
    ) -> Optional[str]:
        """
        Return the zone_id containing the foot position of the bounding box.

        Args:
            bbox: (x1, y1, x2, y2) in pixel coordinates
            frame_shape: (height, width) of the source frame

        Returns:
            zone_id string if foot position is inside a zone polygon.
            None if outside all zones or camera has no zones.
        """
        if not self._camera_zones.zones:
            return None

        frame_h, frame_w = frame_shape[:2]
        x1, y1, x2, y2 = bbox

        # Use bottom-centre as foot position (more accurate zone attribution)
        foot_x = ((x1 + x2) / 2.0) / frame_w   # Normalised 0.0–1.0
        foot_y = y2 / frame_h                    # Bottom of bbox

        point = Point(foot_x, foot_y)

        # Test each zone polygon — return first match
        for zone_id, polygon in self._camera_zones.zones.items():
            if polygon.contains(point):
                return zone_id

        return None

    def get_threshold_y(self) -> Optional[float]:
        """Return the normalised entry/exit threshold Y coordinate."""
        return self._camera_zones.threshold_y

    def is_entry_camera(self) -> bool:
        """Return True if this camera is an entry/exit threshold camera."""
        return self._camera_zones.camera_type == "entry_exit"

    @staticmethod
    def load_all_store_zones(
        layout_path: Path,
        store_id: str,
    ) -> list[str]:
        """
        Return all zone names for a store across all cameras.
        Used by anomaly detection for dead-zone checking.
        """
        if not layout_path.exists():
            return []
        raw = json.loads(layout_path.read_text())
        store = raw.get(store_id, {})
        all_zones: set[str] = set()
        for cam_cfg in store.get("cameras", {}).values():
            for zone_id in cam_cfg.get("zones", {}):
                all_zones.add(zone_id)
        return sorted(all_zones)
