import pathlib

from pipeline.events import EventDetector
from pipeline.rules import ProcessConfig, RuleEngine, summarize

from tests.synthetic import generate_cycles

CONFIG = ProcessConfig.from_yaml(
    str(pathlib.Path(__file__).parent.parent / "configs" / "example_process.yaml")
)


def run_engine(frames):
    det = EventDetector(rois=CONFIG.rois, keypoints=CONFIG.keypoints)
    events = det.process(iter(frames))
    return RuleEngine(CONFIG).run(events)


def test_detects_all_cycles():
    cycles = run_engine(generate_cycles(n_cycles=10))
    complete = [c for c in cycles if c.status == "complete"]
    assert len(complete) == 10
    for c in complete:
        assert [s["step"] for s in c.steps] == ["pick", "place"]


def test_cycle_and_step_durations():
    # Measured dwell = hold time + the travel portion inside the ROI +
    # hysteresis lag, so tolerance covers ~1 travel duration on top of truth.
    cycles = run_engine(generate_cycles(n_cycles=8, pick_s=1.5, place_s=2.5))
    report = summarize(cycles)
    assert report["cycles_complete"] == 8
    assert abs(report["step_time_median"]["pick"] - 1.5) < 1.2
    assert abs(report["step_time_median"]["place"] - 2.5) < 1.2
    # what matters for work-time analysis is repeatability across cycles
    spread = report["cycle_time_max"] - report["cycle_time_min"]
    assert spread < 0.5


def test_step_timeout_flagged_as_anomaly():
    # pick takes 7s > max_duration 5s
    cycles = run_engine(generate_cycles(n_cycles=2, pick_s=7.0))
    anomalous = [c for c in cycles if c.status == "anomalous"]
    assert len(anomalous) == 2
    types = {a["type"] for c in anomalous for a in c.anomalies}
    assert types == {"step_timeout"}


def test_video_ending_mid_cycle_is_incomplete():
    frames = generate_cycles(n_cycles=3)
    cut = int(len(frames) * 0.85)   # cut during the 3rd cycle
    cycles = run_engine(frames[:cut])
    assert sum(c.status == "complete" for c in cycles) == 2
    assert cycles[-1].status == "incomplete"


def test_summarize_median():
    cycles = run_engine(generate_cycles(n_cycles=5))
    report = summarize(cycles)
    assert report["cycles_total"] == 5
    assert report["cycle_time_median"] is not None
    assert report["anomalies"] == 0
