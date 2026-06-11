"""Synthetic keypoint-stream generator for testing the event/rule layers.

Simulates a worker's right wrist cycling between a parts bin, a fixture and
a rest position, with gaussian jitter — so the hysteresis logic and the
state machine are exercised the same way real perception output would.
Geometry matches configs/example_process.yaml.
"""
from __future__ import annotations

import random

from pipeline.schemas import FramePerception

FPS = 10.0
BIN_CENTER = (0.17, 0.55)      # inside parts_bin
FIXTURE_CENTER = (0.60, 0.62)  # inside fixture
REST = (0.85, 0.25)            # outside both ROIs


def _frame(x, y, t, idx, jitter, rng):
    return FramePerception(
        frame_idx=idx,
        t=round(t, 4),
        keypoints={"right_wrist": [x + rng.gauss(0, jitter),
                                   y + rng.gauss(0, jitter), 0.95],
                   "left_wrist": [0.9, 0.9, 0.95]},
    )


def _segment(target, hold_s, t0, frame0, jitter, rng):
    """Frames holding the wrist near `target` for hold_s seconds."""
    n = int(hold_s * FPS)
    return [_frame(target[0], target[1], t0 + i / FPS, frame0 + i, jitter, rng)
            for i in range(n)]


def _travel(src, dst, travel_s, t0, frame0, jitter, rng):
    """Frames moving the wrist linearly from src to dst (real hands don't
    teleport — without this the ROI exit/enter event order is unrealistic)."""
    n = int(travel_s * FPS)
    frames = []
    for i in range(n):
        a = (i + 1) / (n + 1)
        x = src[0] + (dst[0] - src[0]) * a
        y = src[1] + (dst[1] - src[1]) * a
        frames.append(_frame(x, y, t0 + i / FPS, frame0 + i, jitter, rng))
    return frames


def generate_cycles(
    n_cycles: int = 10,
    pick_s: float = 1.5,
    place_s: float = 2.5,
    rest_s: float = 1.0,
    travel_s: float = 0.8,
    jitter: float = 0.01,
    seed: int = 42,
) -> list[FramePerception]:
    rng = random.Random(seed)
    frames: list[FramePerception] = []
    t, idx = 0.0, 0
    pos = REST

    def emit(seg, hold):
        nonlocal t, idx
        frames.extend(seg)
        idx += len(seg)
        t = round(t + hold, 4)

    for _ in range(n_cycles):
        for target, hold in [(BIN_CENTER, pick_s),
                             (FIXTURE_CENTER, place_s),
                             (REST, rest_s)]:
            emit(_travel(pos, target, travel_s, t, idx, jitter, rng), travel_s)
            emit(_segment(target, hold, t, idx, jitter, rng), hold)
            pos = target
    return frames
