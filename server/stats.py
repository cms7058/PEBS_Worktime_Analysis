"""Statistics service over historical cycle data (阶段 4 的核心).

Work-time data is typically right-skewed (occasional long pauses), so the
headline numbers are median and percentiles; the mean is reported but never
the headline. Normality is tested on both the raw and log-transformed data —
stable manual work is usually closer to log-normal.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
from scipy import stats as sps

MIN_SAMPLES = 5          # below this, only report counts
BOOTSTRAP_N = 2000


def _round(x: Optional[float], nd: int = 3) -> Optional[float]:
    return None if x is None else round(float(x), nd)


def _bootstrap_median_ci(xs: np.ndarray, level: float = 0.95) -> tuple[float, float]:
    rng = np.random.default_rng(0)
    medians = np.median(
        rng.choice(xs, size=(BOOTSTRAP_N, len(xs)), replace=True), axis=1)
    lo, hi = np.percentile(medians, [(1 - level) / 2 * 100, (1 + level) / 2 * 100])
    return float(lo), float(hi)


def _normality(xs: np.ndarray) -> dict:
    """Shapiro-Wilk on raw and log-transformed data + shape diagnostics."""
    out: dict = {}
    if len(xs) >= 8:   # shapiro needs a reasonable sample
        w, p = sps.shapiro(xs)
        out["shapiro_raw"] = {"W": _round(w, 4), "p": _round(p, 4),
                              "normal_at_0.05": bool(p > 0.05)}
        if (xs > 0).all():
            wl, pl = sps.shapiro(np.log(xs))
            out["shapiro_log"] = {"W": _round(wl, 4), "p": _round(pl, 4),
                                  "lognormal_at_0.05": bool(pl > 0.05)}
    out["skewness"] = _round(sps.skew(xs))
    out["kurtosis_excess"] = _round(sps.kurtosis(xs))
    # Crude bimodality flag: dip statistic is overkill for the MVP; a large
    # gap between the two largest histogram modes is a useful first signal.
    hist, edges = np.histogram(xs, bins="auto")
    peaks = [i for i in range(len(hist))
             if hist[i] > 0
             and (i == 0 or hist[i] >= hist[i - 1])
             and (i == len(hist) - 1 or hist[i] >= hist[i + 1])]
    out["suspected_bimodal"] = bool(
        len(peaks) >= 2 and min(hist[p] for p in peaks[:2]) >= max(2, 0.15 * hist.max())
        and any(hist[i] <= 0.5 * min(hist[peaks[0]], hist[peaks[-1]])
                for i in range(peaks[0], peaks[-1] + 1))
    )
    return out


def describe(durations: list[float]) -> dict:
    """Full descriptive report for a list of cycle/step durations (seconds)."""
    xs = np.asarray([d for d in durations if d is not None], dtype=float)
    report: dict = {"n": int(len(xs))}
    if len(xs) == 0:
        return report
    q = np.percentile(xs, [25, 50, 75, 90])
    report.update({
        "median": _round(q[1]),
        "p25": _round(q[0]), "p75": _round(q[2]), "p90": _round(q[3]),
        "mean": _round(xs.mean()), "std": _round(xs.std(ddof=1) if len(xs) > 1 else 0),
        "cv": _round(xs.std(ddof=1) / xs.mean()) if len(xs) > 1 and xs.mean() else None,
        "min": _round(xs.min()), "max": _round(xs.max()),
    })
    if len(xs) >= MIN_SAMPLES:
        lo, hi = _bootstrap_median_ci(xs)
        report["median_ci95"] = [_round(lo), _round(hi)]
        report["distribution"] = _normality(xs)
        # histogram data for the frontend
        hist, edges = np.histogram(xs, bins="auto")
        report["histogram"] = {
            "counts": hist.tolist(),
            "edges": [_round(e) for e in edges],
        }
    return report


def process_statistics(cycles: list[dict]) -> dict:
    """Statistics for one process: cycle level + per-step level.

    `cycles` are DB rows (dicts with duration/status/steps). Only complete
    cycles enter the timing statistics; other statuses are counted so nothing
    silently disappears.
    """
    by_status: dict[str, int] = {}
    for c in cycles:
        by_status[c["status"]] = by_status.get(c["status"], 0) + 1
    complete = [c for c in cycles if c["status"] == "complete" and c["duration"]]

    step_durations: dict[str, list[float]] = {}
    for c in complete:
        for s in c["steps"]:
            if s.get("duration") is not None:
                step_durations.setdefault(s["step"], []).append(s["duration"])

    return {
        "cycles_by_status": by_status,
        "cycle_time": describe([c["duration"] for c in complete]),
        "step_time": {name: describe(ds) for name, ds in step_durations.items()},
    }
