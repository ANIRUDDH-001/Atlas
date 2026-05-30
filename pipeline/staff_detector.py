"""
HSV-based staff uniform detection.
Implemented fully in: 03_06_staff_detector.md
"""
import numpy as np
from pipeline.config import PipelineConfig


class StaffDetector:
    def __init__(self, config: PipelineConfig):
        ...

    def is_staff(self, frame: np.ndarray, bbox: tuple) -> bool:
        """
        Returns True if the person in bbox is classified as staff.
        Uses HSV histogram of upper-body crop.
        """
        ...
