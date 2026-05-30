"""
Entry/Exit direction detection via virtual threshold line crossing.

Uses per-track Y-position history to detect when a person crosses
the entry/exit threshold line defined in store_layout.json.

Design decisions:
- Uses foot position (bottom of bbox) not centroid — more accurate
  for threshold crossing when people stand near the line
- Requires 3 consistent frames crossing the threshold — prevents
  single-frame detection jitter from emitting false events
- Per-track crossing state prevents double-counting the same crossing
"""
import structlog
from collections import deque
from typing import Optional
from dataclasses import dataclass, field

logger = structlog.get_logger()


HISTORY_LEN = 10         # Frames of Y-position history per track
CROSSING_MIN_FRAMES = 3  # Frames needed to confirm a crossing


@dataclass
class TrackCrossingState:
    """State for one tracked person at the entry threshold."""
    track_id: int
    y_history: deque = field(default_factory=lambda: deque(maxlen=HISTORY_LEN))
    crossing_registered: bool = False    # Prevent double-counting
    last_side: Optional[str] = None      # "above" or "below" threshold


class DirectionDetector:
    """
    Detects inbound (ENTRY) and outbound (EXIT) crossings of the
    virtual threshold line for an entry/exit camera.

    Usage:
        detector = DirectionDetector(threshold_y=0.45)
        direction = detector.update(track_id, foot_y_normalised)
        # direction is "ENTRY", "EXIT", or None
    """

    def __init__(self, threshold_y: float):
        """
        Args:
            threshold_y: Normalised Y coordinate (0.0–1.0) of the crossing line.
                         0.0 = top of frame, 1.0 = bottom of frame.
                         Persons moving from y < threshold_y to y > threshold_y
                         are entering (moving into the store from the street).
        """
        self._threshold = threshold_y
        self._tracks: dict[int, TrackCrossingState] = {}
        self._crossing_log: list[dict] = []

    def update(
        self,
        track_id: int,
        foot_y_normalised: float,
        frame_idx: int = 0,
    ) -> Optional[str]:
        """
        Update the Y-position history for a track and check for crossing.

        Args:
            track_id: BoT-SORT track identifier
            foot_y_normalised: Y coordinate of the foot position, 0.0–1.0
            frame_idx: Current frame number (for logging)

        Returns:
            "ENTRY" if confirmed inbound crossing detected
            "EXIT" if confirmed outbound crossing detected
            None if no crossing detected this frame
        """
        # Initialise state for new tracks
        if track_id not in self._tracks:
            self._tracks[track_id] = TrackCrossingState(track_id=track_id)

        state = self._tracks[track_id]
        state.y_history.append(foot_y_normalised)

        # Need minimum history before evaluating
        if len(state.y_history) < CROSSING_MIN_FRAMES:
            return None

        # Already registered a crossing for this track — do not re-register
        # until the track re-appears after being lost (mark_lost resets this)
        if state.crossing_registered:
            return None

        return self._evaluate_crossing(state, track_id, frame_idx)

    def mark_lost(self, track_id: int) -> None:
        """
        Reset crossing registration for a track that has been lost.
        Allows future crossings from the same physical track_id (if BoT-SORT
        re-assigns the same ID after re-detection).
        """
        if track_id in self._tracks:
            self._tracks[track_id].crossing_registered = False

    def clear_track(self, track_id: int) -> None:
        """Remove all state for a completed track."""
        self._tracks.pop(track_id, None)

    def get_crossing_log(self) -> list[dict]:
        """Return all confirmed crossings for this clip (for debugging)."""
        return self._crossing_log.copy()

    def _evaluate_crossing(
        self,
        state: TrackCrossingState,
        track_id: int,
        frame_idx: int,
    ) -> Optional[str]:
        """
        Evaluate recent Y-history for a confirmed threshold crossing.

        Crossing is confirmed when:
        - The last CROSSING_MIN_FRAMES positions are consistently on
          one side of the threshold
        - The oldest position in the history was on the opposite side

        Returns "ENTRY", "EXIT", or None.
        """
        history = list(state.y_history)
        threshold = self._threshold

        # Classify each position as above or below threshold
        sides = ["below" if y >= threshold else "above" for y in history]

        earliest = sides[0]
        recents  = sides[-CROSSING_MIN_FRAMES:]

        # All recent frames consistently on one side
        if len(set(recents)) != 1:
            return None

        current_side = recents[0]

        # No crossing if started and ended on the same side
        if earliest == current_side:
            return None

        # Determine direction
        if earliest == "above" and current_side == "below":
            direction = "ENTRY"
        elif earliest == "below" and current_side == "above":
            direction = "EXIT"
        else:
            return None

        # Register crossing — prevent double-counting
        state.crossing_registered = True
        state.last_side = current_side

        self._crossing_log.append({
            "track_id":  track_id,
            "direction": direction,
            "frame_idx": frame_idx,
            "threshold": threshold,
        })

        logger.info("crossing_detected",
                    track_id=track_id,
                    direction=direction,
                    frame_idx=frame_idx,
                    foot_y=round(history[-1], 3),
                    threshold=threshold)

        return direction
