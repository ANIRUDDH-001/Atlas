# PROMPT: Ensure edge cases are handled
# CHANGES MADE: Added testing blocks and verified output schema
"""
Tests for staff detection.

Ground truth:
  - Brigade Road store has 5 salespersons.
  - Staff wear a distinctive uniform colour (purple / as per calibration).
  - Staff events should be ~15-25% of total events in a full-day pipeline run.
  - A pure-customer clip (no staff visible) should return 0 staff events.

Note: Live DB query returned 0 total events (pipeline not run yet).
"""
import pytest
import numpy as np
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pipeline.staff_detector import StaffDetector
from pipeline.config import get_pipeline_config


@pytest.fixture
def staff_det():
    cfg = get_pipeline_config()
    return StaffDetector(cfg)


@pytest.fixture
def cfg():
    return get_pipeline_config()


class TestStaffDetectorUnit:

    def test_purple_crop_classified_as_staff(self, staff_det):
        """A crop containing predominantly purple pixels must return True."""
        # BGR value for a purple similar to retail uniform (H=150, S=180, V=180)
        purple_bgr = np.full((80, 40, 3), [180, 53, 180], dtype=np.uint8)
        result = staff_det.is_staff(purple_bgr, (0, 0, 40, 80))
        assert result is True, (
            "Purple crop was not classified as staff. "
            "Check staff_hue_lower/upper and staff_color_ratio_threshold in config."
        )

    def test_blue_crop_not_classified_as_staff(self, staff_det):
        """A blue crop must NOT be classified as staff."""
        blue_bgr = np.full((80, 40, 3), [180, 50, 20], dtype=np.uint8)
        result = staff_det.is_staff(blue_bgr, (0, 0, 40, 80))
        assert result is False, "Blue crop was incorrectly classified as staff"

    def test_black_crop_not_classified_as_staff(self, staff_det):
        """A black crop (no colour) must not be classified as staff."""
        black_bgr = np.full((80, 40, 3), [20, 20, 20], dtype=np.uint8)
        result = staff_det.is_staff(black_bgr, (0, 0, 40, 80))
        assert result is False, "Plain black crop should not be staff"

    def test_white_crop_not_classified_as_staff(self, staff_det):
        """A white crop must not be classified as staff."""
        white_bgr = np.full((80, 40, 3), [240, 240, 240], dtype=np.uint8)
        result = staff_det.is_staff(white_bgr, (0, 0, 40, 80))
        assert result is False, "White crop should not be staff"

    def test_empty_crop_returns_false(self, staff_det):
        """An empty crop must return False without raising."""
        empty = np.zeros((0, 0, 3), dtype=np.uint8)
        result = staff_det.is_staff(empty, (0, 0, 0, 0))
        assert result is False

    def test_tiny_crop_returns_false(self, staff_det):
        """Crops smaller than the minimum size must return False."""
        tiny = np.full((8, 5, 3), [150, 30, 150], dtype=np.uint8)
        result = staff_det.is_staff(tiny, (0, 0, 5, 8))
        assert result is False, (
            "Crop of 8x5 is below minimum size — should return False "
            "regardless of colour to avoid noisy classifications"
        )

    def test_is_staff_does_not_raise_on_any_input(self, staff_det):
        """is_staff() must never raise, regardless of input shape."""
        for shape in [(10, 10, 3), (100, 50, 3), (1, 1, 3), (200, 200, 3)]:
            crop = np.random.randint(0, 255, shape, dtype=np.uint8)
            try:
                staff_det.is_staff(crop, (0, 0, shape[1], shape[0]))
            except Exception as e:
                pytest.fail(f"is_staff raised on shape {shape}: {e}")


class TestStaffDetectorConfig:

    def test_hue_range_sensible(self, cfg):
        """HSV hue range must be within the plausible purple/uniform band."""
        assert cfg.staff_hue_lower >= 100, (
            f"staff_hue_lower={cfg.staff_hue_lower} is too low — "
            "values below 100 encroach on green/teal"
        )
        assert cfg.staff_hue_upper <= 180, (
            f"staff_hue_upper={cfg.staff_hue_upper} exceeds OpenCV max hue (180)"
        )
        assert cfg.staff_hue_lower < cfg.staff_hue_upper, (
            "staff_hue_lower must be less than staff_hue_upper"
        )

    def test_ratio_threshold_is_reachable(self, cfg):
        """Threshold must be low enough to be reachable on small CCTV crops."""
        assert cfg.staff_color_ratio_threshold <= 0.30, (
            f"staff_color_ratio_threshold={cfg.staff_color_ratio_threshold} "
            "is too high for typical 30-60px CCTV crops at retail distance. "
            "Values above 0.30 will miss most real staff."
        )
        assert cfg.staff_color_ratio_threshold >= 0.10, (
            f"staff_color_ratio_threshold={cfg.staff_color_ratio_threshold} "
            "is too low — will cause false positives for customers "
            "wearing similar colours"
        )
