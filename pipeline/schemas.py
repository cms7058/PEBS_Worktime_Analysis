"""Core data structures shared across the pipeline stages.

Pipeline data flow:
    video -> perception -> FramePerception stream (JSONL)
          -> events     -> AtomicEvent stream
          -> rules      -> StepRecord / CycleRecord
All coordinates are normalized to [0, 1] relative to frame width/height,
so ROI configs are resolution-independent.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional
import json


@dataclass
class Keypoint:
    name: str
    x: float
    y: float
    confidence: float

    def to_list(self) -> list:
        return [round(self.x, 5), round(self.y, 5), round(self.confidence, 4)]


@dataclass
class FramePerception:
    """Perception output for a single video frame."""
    frame_idx: int
    t: float                       # seconds from video start
    keypoints: dict[str, list]     # name -> [x, y, confidence]
    person_detected: bool = True

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, line: str) -> "FramePerception":
        return cls(**json.loads(line))


@dataclass
class AtomicEvent:
    """An atomic semantic event derived from the keypoint stream."""
    t: float
    event: str        # roi_enter | roi_exit | dwell
    roi: str
    keypoint: str
    frame_idx: int
    duration: float = 0.0   # for dwell / exit events: time spent inside

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


@dataclass
class StepRecord:
    """One completed (or aborted) work step inside a cycle."""
    step: str
    t_start: float
    t_end: Optional[float]
    duration: Optional[float]
    status: str = "ok"            # ok | timeout | skipped
    keypoint: str = ""


@dataclass
class CycleRecord:
    """One full work cycle: the unit of work-time measurement."""
    cycle_idx: int
    t_start: float
    t_end: Optional[float]
    duration: Optional[float]
    steps: list = field(default_factory=list)   # list[StepRecord as dict]
    status: str = "complete"                    # complete | incomplete | anomalous
    anomalies: list = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)
