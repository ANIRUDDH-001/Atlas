"""
HSV-based staff uniform classification.

Classifies a detected person as staff or customer based on the dominant
colour in the upper body region of their bounding box crop.

Design rationale (documented in CHOICES.md):
- Chose HSV colour histogram over trained classifier because:
  (a) No labelled staff/customer training data provided
  (b) Retail staff uniforms have consistent, distinct colours
  (c) HSV is lighting-invariant (hue channel stable under fluorescent/natural mix)
  (d) Runs in < 1ms per detection on CPU
- Conservative threshold (0.25 ratio): prefer false negative (call a
  staff member a customer) over false positive (exclude real customer).
  Rationale: false positives directly harm conversion_rate accuracy.
"""
import cv2
import numpy as np
import structlog
from pipeline.config import PipelineConfig

logger = structlog.get_logger()


class StaffDetector:
    """
    Classifies bounding boxes as staff or customer using HSV colour analysis.

    Usage:
        detector = StaffDetector(config)
        is_staff = detector.is_staff(frame, bbox)
    """

    def __init__(self, config: PipelineConfig):
        self.config = config
        self._lower = np.array([
            config.staff_hue_lower,
            config.staff_saturation_lower,
            50,   # Minimum value (brightness)
        ], dtype=np.uint8)
        self._upper = np.array([
            config.staff_hue_upper,
            255,
            255,
        ], dtype=np.uint8)
        self._threshold = config.staff_color_ratio_threshold
        self._black_v_upper = config.staff_black_value_upper
        self._black_s_upper = config.staff_black_sat_upper
        logger.info("staff_detector_initialized",
                    hue_range=f"{config.staff_hue_lower}–{config.staff_hue_upper}",
                    black_thresh=f"V<{self._black_v_upper}, S<{self._black_s_upper}",
                    threshold=self._threshold)

    def is_staff(self, frame: np.ndarray, bbox: tuple) -> bool:
        """
        Returns True if the person in bbox is classified as staff.

        Args:
            frame: Full BGR video frame (numpy array)
            bbox: Bounding box as (x1, y1, x2, y2) in pixel coordinates

        Returns:
            True if staff classification confidence exceeds threshold.
            Returns False (assume customer) if crop is invalid.
        """
        if frame is None:
            return False

        crop = self._extract_upper_body(frame, bbox)
        if crop is None:
            return False

        ratio = self._compute_color_ratio(crop)
        is_staff_flag = ratio > self._threshold

        if is_staff_flag:
            logger.debug("staff_detected",
                         ratio=round(ratio, 3),
                         bbox=bbox)

        return is_staff_flag

    def _extract_upper_body(
        self,
        frame: np.ndarray,
        bbox: tuple,
    ) -> np.ndarray | None:
        """
        Extract the upper 40% of the bounding box as the uniform region.

        Returns None if the crop region is invalid.
        """
        x1, y1, x2, y2 = map(int, bbox)

        # Clamp to frame boundaries
        h, w = frame.shape[:2]
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(w, x2)
        y2 = min(h, y2)

        if x2 <= x1 or y2 <= y1:
            return None

        # Minimum crop size guard (applied to full body)
        if (y2 - y1) < 20 or (x2 - x1) < 10:
            return None

        # Upper 40% of the bounding box
        body_height = y2 - y1
        upper_y2 = y1 + int(body_height * 0.40)

        if upper_y2 <= y1:
            return None

        crop = frame[y1:upper_y2, x1:x2]

        # Upper body size guard
        if crop.shape[0] == 0 or crop.shape[1] == 0:
            return None

        return crop

    def _compute_color_ratio(self, crop_bgr: np.ndarray) -> float:
        """
        Compute the fraction of pixels in the crop that match EITHER
        the staff uniform HSV colour range OR black clothing (low V, low S).
        """
        hsv = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2HSV)
        
        # 1. Original hue-based mask (fallback)
        mask_hue = cv2.inRange(hsv, self._lower, self._upper)
        
        # 2. Black clothing mask (low brightness, low saturation)
        # H can be anything (0-179)
        # S must be low (0 to staff_black_sat_upper)
        # V must be low (0 to staff_black_value_upper)
        lower_black = np.array([0, 0, 0], dtype=np.uint8)
        upper_black = np.array([179, self._black_s_upper, self._black_v_upper], dtype=np.uint8)
        mask_black = cv2.inRange(hsv, lower_black, upper_black)
        
        # Combine masks (pixel is staff if it matches EITHER rule)
        mask_combined = cv2.bitwise_or(mask_hue, mask_black)
        
        total_pixels = crop_bgr.shape[0] * crop_bgr.shape[1]
        if total_pixels == 0:
            return 0.0
            
        matched = int(np.sum(mask_combined > 0))
        return matched / total_pixels

    def calibrate(
        self,
        known_staff_crops: list[np.ndarray],
        known_customer_crops: list[np.ndarray],
    ) -> float:
        """
        Utility: compute the optimal threshold given labelled crops.
        Returns the recommended threshold value.
        Only used during offline calibration, not in production pipeline.
        """
        staff_ratios    = [self._compute_color_ratio(c) for c in known_staff_crops
                           if c is not None]
        customer_ratios = [self._compute_color_ratio(c) for c in known_customer_crops
                           if c is not None]

        if not staff_ratios or not customer_ratios:
            return self._threshold

        # Find midpoint between max customer ratio and min staff ratio
        max_customer = max(customer_ratios)
        min_staff    = min(staff_ratios)
        recommended  = (max_customer + min_staff) / 2

        logger.info("calibration_result",
                    staff_count=len(staff_ratios),
                    customer_count=len(customer_ratios),
                    max_customer_ratio=round(max_customer, 3),
                    min_staff_ratio=round(min_staff, 3),
                    recommended_threshold=round(recommended, 3))

        return recommended
