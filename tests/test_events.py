from pipeline.events import ROI, EventDetector
from pipeline.schemas import FramePerception

from tests.synthetic import generate_cycles

ROIS = [
    ROI("parts_bin", (0.05, 0.35, 0.30, 0.75)),
    ROI("fixture", (0.45, 0.40, 0.75, 0.85)),
]


def detect(frames, **kw):
    det = EventDetector(rois=ROIS, keypoints=["right_wrist", "left_wrist"], **kw)
    return list(det.process(iter(frames)))


def test_enter_exit_pairs_per_cycle():
    events = detect(generate_cycles(n_cycles=5))
    bin_enters = [e for e in events if e.event == "roi_enter" and e.roi == "parts_bin"]
    bin_exits = [e for e in events if e.event == "roi_exit" and e.roi == "parts_bin"]
    fix_enters = [e for e in events if e.event == "roi_enter" and e.roi == "fixture"]
    assert len(bin_enters) == len(bin_exits) == len(fix_enters) == 5


def test_exit_duration_close_to_dwell():
    events = detect(generate_cycles(n_cycles=3, pick_s=2.0))
    durs = [e.duration for e in events if e.event == "roi_exit" and e.roi == "parts_bin"]
    assert len(durs) == 3
    # hysteresis trims edges; dwell should still be within ~0.8s of truth
    assert all(abs(d - 2.0) < 0.8 for d in durs)


def test_single_frame_jitter_is_absorbed():
    """One stray sample outside the ROI must not fire an exit/enter pair."""
    frames = generate_cycles(n_cycles=1, pick_s=3.0, jitter=0.0)
    # corrupt one mid-pick frame: teleport wrist far away for a single sample
    frames[15].keypoints["right_wrist"] = [0.95, 0.95, 0.95]
    events = detect(frames)
    bin_events = [e for e in events if e.roi == "parts_bin"]
    assert [e.event for e in bin_events] == ["roi_enter", "roi_exit"]


def test_low_confidence_samples_hold_state():
    frames = generate_cycles(n_cycles=1, pick_s=3.0)
    for f in frames[10:20]:
        f.keypoints["right_wrist"][2] = 0.1   # tracking dropout mid-pick
    events = detect(frames)
    bin_events = [e for e in events if e.roi == "parts_bin"]
    assert [e.event for e in bin_events] == ["roi_enter", "roi_exit"]
