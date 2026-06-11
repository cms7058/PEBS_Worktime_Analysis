"""Event layer: keypoint stream + ROI config -> atomic event stream.

Turns noisy per-frame geometry into clean semantic events (roi_enter /
roi_exit) using hysteresis: a keypoint must stay inside an ROI for
`enter_frames` consecutive samples to fire an enter, and outside for
`exit_frames` samples to fire an exit. This absorbs keypoint jitter and
single-frame tracking dropouts.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Iterator

from .schemas import AtomicEvent, FramePerception


@dataclass
class ROI:
    name: str
    rect: tuple[float, float, float, float]   # normalized x1, y1, x2, y2

    def contains(self, x: float, y: float) -> bool:
        x1, y1, x2, y2 = self.rect
        return x1 <= x <= x2 and y1 <= y <= y2


@dataclass
class _TrackState:
    inside: bool = False
    streak: int = 0           # consecutive samples contradicting current state
    streak_t: float = 0.0     # when the contradicting streak began
    streak_frame: int = 0
    t_entered: float = 0.0


class EventDetector:
    def __init__(
        self,
        rois: list[ROI],
        keypoints: list[str],
        enter_frames: int = 3,
        exit_frames: int = 5,
        min_confidence: float = 0.5,
    ):
        self.rois = rois
        self.keypoints = keypoints
        self.enter_frames = enter_frames
        self.exit_frames = exit_frames
        self.min_confidence = min_confidence
        self._state: dict[tuple[str, str], _TrackState] = {
            (kp, roi.name): _TrackState() for kp in keypoints for roi in rois
        }

    def process(self, frames: Iterable[FramePerception]) -> Iterator[AtomicEvent]:
        for frame in frames:
            for kp_name in self.keypoints:
                kp = frame.keypoints.get(kp_name)
                if kp is None or kp[2] < self.min_confidence:
                    continue   # low-confidence sample: hold current state
                for roi in self.rois:
                    state = self._state[(kp_name, roi.name)]
                    inside_now = roi.contains(kp[0], kp[1])
                    if inside_now == state.inside:
                        state.streak = 0
                        continue
                    state.streak += 1
                    if state.streak == 1:
                        state.streak_t = frame.t
                        state.streak_frame = frame.frame_idx
                    threshold = self.enter_frames if not state.inside else self.exit_frames
                    if state.streak < threshold:
                        continue
                    # Timestamp the event at the start of the confirming
                    # streak (when the change physically happened), not at
                    # confirmation time — otherwise fast hand movements emit
                    # exit/enter events in the wrong order across ROIs and
                    # dwell durations are padded by the hysteresis lag.
                    state.inside = inside_now
                    state.streak = 0
                    if inside_now:
                        state.t_entered = state.streak_t
                        yield AtomicEvent(
                            t=state.streak_t, event="roi_enter", roi=roi.name,
                            keypoint=kp_name, frame_idx=state.streak_frame,
                        )
                    else:
                        yield AtomicEvent(
                            t=state.streak_t, event="roi_exit", roi=roi.name,
                            keypoint=kp_name, frame_idx=state.streak_frame,
                            duration=round(state.streak_t - state.t_entered, 4),
                        )
