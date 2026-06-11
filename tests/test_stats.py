import numpy as np

from server.stats import describe, process_statistics


def test_describe_basic():
    rng = np.random.default_rng(1)
    xs = rng.normal(10, 1, 200).tolist()
    r = describe(xs)
    assert r["n"] == 200
    assert abs(r["median"] - 10) < 0.3
    lo, hi = r["median_ci95"]
    assert lo < r["median"] < hi
    assert (hi - lo) < 0.6   # CI should be tight at n=200
    assert r["distribution"]["shapiro_raw"]["normal_at_0.05"] is True


def test_describe_lognormal_detected():
    rng = np.random.default_rng(2)
    xs = np.exp(rng.normal(2, 0.5, 300)).tolist()   # strongly right-skewed
    r = describe(xs)
    d = r["distribution"]
    assert d["shapiro_raw"]["normal_at_0.05"] is False
    assert d["shapiro_log"]["lognormal_at_0.05"] is True
    assert d["skewness"] > 1


def test_describe_small_sample_no_ci():
    r = describe([1.0, 2.0, 3.0])
    assert r["n"] == 3
    assert r["median"] == 2.0
    assert "median_ci95" not in r


def test_describe_empty():
    assert describe([]) == {"n": 0}


def _cycle(duration, status="complete", steps=None):
    if steps is None and duration is not None:
        steps = [{"step": "pick", "duration": duration * 0.4},
                 {"step": "place", "duration": duration * 0.6}]
    return {"duration": duration, "status": status, "steps": steps or []}


def test_process_statistics_aggregates_steps_and_statuses():
    cycles = [_cycle(10.0 + i * 0.1) for i in range(20)]
    cycles.append(_cycle(None, status="incomplete", steps=[]))
    r = process_statistics(cycles)
    assert r["cycles_by_status"] == {"complete": 20, "incomplete": 1}
    assert r["cycle_time"]["n"] == 20
    assert set(r["step_time"]) == {"pick", "place"}
    assert abs(r["step_time"]["pick"]["median"] - 4.4) < 0.2
