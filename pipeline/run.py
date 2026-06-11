"""End-to-end CLI: video + process config -> cycles + summary.

usage:
    python -m pipeline.run <video> <process_config.yaml> [--out DIR] [--fps N]
    python -m pipeline.run --keypoints <stream.jsonl> <process_config.yaml> ...

The second form skips perception and replays a saved keypoint stream, which
is how the event/rule layers are developed and tested independently.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .events import EventDetector
from .rules import ProcessConfig, RuleEngine, summarize
from .schemas import FramePerception


def load_keypoint_stream(path: Path):
    with open(path) as f:
        for line in f:
            if line.strip():
                yield FramePerception.from_json(line)


def main() -> None:
    ap = argparse.ArgumentParser(description="PEBS work-time analysis pipeline")
    ap.add_argument("source", help="video file, or keypoint JSONL with --keypoints")
    ap.add_argument("config", help="process config YAML")
    ap.add_argument("--keypoints", action="store_true",
                    help="source is a saved keypoint stream, skip perception")
    ap.add_argument("--out", default="data/outputs", help="output directory")
    ap.add_argument("--fps", type=float, default=10.0,
                    help="perception sampling fps (video mode)")
    ap.add_argument("--backend", default="pose", choices=["pose", "hands"],
                    help="pose: body visible; hands: close-up hand-only views")
    args = ap.parse_args()

    cfg = ProcessConfig.from_yaml(args.config)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(args.source).stem

    if args.keypoints:
        frames = load_keypoint_stream(Path(args.source))
    else:
        from .perception import analyze_video
        frames = analyze_video(args.source, sample_fps=args.fps,
                               backend=args.backend)

    detector = EventDetector(rois=cfg.rois, keypoints=cfg.keypoints)
    # Retroactive timestamps mean emission order can differ from event time;
    # the rule engine needs them in chronological order.
    events = sorted(detector.process(frames), key=lambda e: (e.t, e.frame_idx))
    with open(out_dir / f"{stem}.events.jsonl", "w") as f:
        for ev in events:
            f.write(ev.to_json() + "\n")

    cycles = RuleEngine(cfg).run(iter(events))
    with open(out_dir / f"{stem}.cycles.jsonl", "w") as f:
        for c in cycles:
            f.write(c.to_json() + "\n")

    report = summarize(cycles)
    with open(out_dir / f"{stem}.summary.json", "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
