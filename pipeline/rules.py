"""Rule engine: atomic event stream + user-defined step rules -> cycles.

A process is a sequential state machine of work steps. Each step is bounded
by a start event and an end event (matched against the atomic event stream).
A cycle = one full pass through all steps; its duration is the unit work
time. Timeouts and out-of-order events are recorded as anomalies instead of
silently dropped, so every minute of video is accounted for.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Iterable, Optional

import yaml

from .events import ROI
from .schemas import AtomicEvent, CycleRecord, StepRecord


@dataclass
class EventMatcher:
    event: str                      # roi_enter | roi_exit
    roi: str
    keypoint: str = "any"           # any | same | <keypoint name>

    def matches(self, ev: AtomicEvent, bound_keypoint: Optional[str]) -> bool:
        if ev.event != self.event or ev.roi != self.roi:
            return False
        if self.keypoint == "any":
            return True
        if self.keypoint == "same":
            return bound_keypoint is None or ev.keypoint == bound_keypoint
        return ev.keypoint == self.keypoint


@dataclass
class StepRule:
    name: str
    start: EventMatcher
    end: EventMatcher
    max_duration: Optional[float] = None
    # 可选标准工时定义，两种形式（由 PMTS 模块解释，规则引擎不使用）：
    #   {method: modapts, sequence: [M4, G1, ...], allowance: 0.15}
    #   {seconds: 1.2}
    standard: Optional[dict] = None


@dataclass
class ProcessConfig:
    process: str
    keypoints: list[str]
    rois: list[ROI]
    steps: list[StepRule]
    cycle_max_duration: Optional[float] = None

    @classmethod
    def from_yaml(cls, path: str) -> "ProcessConfig":
        with open(path) as f:
            raw = yaml.safe_load(f)
        return cls(
            process=raw["process"],
            keypoints=raw.get("keypoints", ["left_wrist", "right_wrist"]),
            rois=[ROI(r["name"], tuple(r["rect"])) for r in raw["rois"]],
            steps=[
                StepRule(
                    name=s["name"],
                    start=EventMatcher(**s["start"]),
                    end=EventMatcher(**s["end"]),
                    max_duration=s.get("max_duration"),
                    standard=s.get("standard"),
                )
                for s in raw["steps"]
            ],
            cycle_max_duration=raw.get("cycle", {}).get("max_duration"),
        )


class RuleEngine:
    """Consumes atomic events, emits CycleRecords."""

    def __init__(self, config: ProcessConfig):
        self.cfg = config

    def run(self, events: Iterable[AtomicEvent]) -> list[CycleRecord]:
        cycles: list[CycleRecord] = []
        cycle: Optional[CycleRecord] = None
        step_idx = 0                 # index of the step we are waiting on
        in_step = False              # waiting for end (True) or start (False)
        current: Optional[StepRecord] = None

        def close_cycle(status: str, t_end: Optional[float]) -> None:
            nonlocal cycle, step_idx, in_step, current
            if cycle is None:
                return
            if current is not None and current.t_end is None:
                current.status = "incomplete"
                cycle.steps.append(asdict(current))
            cycle.status = status
            cycle.t_end = t_end
            if t_end is not None:
                cycle.duration = round(t_end - cycle.t_start, 4)
            cycles.append(cycle)
            cycle, step_idx, in_step, current = None, 0, False, None

        for ev in events:
            steps = self.cfg.steps
            if not in_step:
                # A first-step start while mid-cycle means the previous cycle
                # never finished: close it as anomalous and begin a new one.
                if cycle is not None and step_idx > 0 and steps[0].start.matches(ev, None):
                    cycle.anomalies.append(
                        {"t": ev.t, "type": "restart",
                         "detail": f"new cycle began while waiting for step '{steps[step_idx].name}'"}
                    )
                    close_cycle("anomalous", ev.t)
                if steps[step_idx].start.matches(ev, None):
                    if step_idx == 0:
                        cycle = CycleRecord(
                            cycle_idx=len(cycles), t_start=ev.t,
                            t_end=None, duration=None,
                        )
                    current = StepRecord(
                        step=steps[step_idx].name, t_start=ev.t,
                        t_end=None, duration=None, keypoint=ev.keypoint,
                    )
                    in_step = True
            else:
                rule = steps[step_idx]
                if rule.end.matches(ev, current.keypoint):
                    current.t_end = ev.t
                    current.duration = round(ev.t - current.t_start, 4)
                    if rule.max_duration and current.duration > rule.max_duration:
                        current.status = "timeout"
                        cycle.anomalies.append(
                            {"t": ev.t, "type": "step_timeout",
                             "detail": f"step '{rule.name}' took {current.duration}s "
                                       f"(max {rule.max_duration}s)"}
                        )
                    cycle.steps.append(asdict(current))
                    current = None
                    in_step = False
                    step_idx += 1
                    if step_idx >= len(steps):
                        close_cycle(
                            "complete" if not cycle.anomalies else "anomalous",
                            ev.t,
                        )

        # End of stream: whatever is still open never finished.
        if cycle is not None:
            cycle.anomalies.append(
                {"t": None, "type": "stream_end", "detail": "video ended mid-cycle"}
            )
            close_cycle("incomplete", None)
        return cycles


def summarize(cycles: list[CycleRecord]) -> dict:
    """Quick work-time summary over the detected cycles."""
    complete = [c for c in cycles if c.status == "complete" and c.duration]
    durations = sorted(c.duration for c in complete)
    step_times: dict[str, list[float]] = {}
    for c in complete:
        for s in c.steps:
            if s["duration"] is not None:
                step_times.setdefault(s["step"], []).append(s["duration"])

    def median(xs: list[float]) -> Optional[float]:
        if not xs:
            return None
        n = len(xs)
        xs = sorted(xs)
        return round((xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2), 4)

    return {
        "cycles_total": len(cycles),
        "cycles_complete": len(complete),
        "cycle_time_median": median(durations),
        "cycle_time_min": durations[0] if durations else None,
        "cycle_time_max": durations[-1] if durations else None,
        "step_time_median": {k: median(v) for k, v in step_times.items()},
        "anomalies": sum(len(c.anomalies) for c in cycles),
    }
