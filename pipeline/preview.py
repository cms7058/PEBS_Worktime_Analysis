"""ROI preview helper: draw the process config's ROIs on a video frame.

Configuring ROIs by guessing normalized coordinates is painful; this renders
them so you can iterate: adjust rect in the YAML -> re-run -> check image.

usage:
    python -m pipeline.preview <video> <process_config.yaml> [--t 5.0] [--out frame.jpg]
Optionally overlays detected keypoints at that timestamp (--pose).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2

from .rules import ProcessConfig

COLORS = [(0, 200, 0), (0, 140, 255), (255, 120, 0), (180, 0, 220)]


def main() -> None:
    ap = argparse.ArgumentParser(description="Preview ROIs on a video frame")
    ap.add_argument("video")
    ap.add_argument("config")
    ap.add_argument("--t", type=float, default=2.0, help="timestamp (s) of the frame")
    ap.add_argument("--out", default=None, help="output image path")
    ap.add_argument("--pose", action="store_true",
                    help="also overlay detected keypoints at that timestamp")
    ap.add_argument("--backend", default="pose", choices=["pose", "hands"],
                    help="keypoint backend for --pose overlay")
    args = ap.parse_args()

    cfg = ProcessConfig.from_yaml(args.config)
    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise SystemExit(f"cannot open video: {args.video}")
    cap.set(cv2.CAP_PROP_POS_MSEC, args.t * 1000)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise SystemExit(f"no frame at t={args.t}s")
    h, w = frame.shape[:2]

    for i, roi in enumerate(cfg.rois):
        x1, y1, x2, y2 = roi.rect
        color = COLORS[i % len(COLORS)]
        cv2.rectangle(frame, (int(x1 * w), int(y1 * h)),
                      (int(x2 * w), int(y2 * h)), color, 2)
        cv2.putText(frame, roi.name, (int(x1 * w) + 4, int(y1 * h) + 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

    if args.pose:
        from .perception import analyze_video
        for fp in analyze_video(args.video, sample_fps=None, backend=args.backend):
            if fp.t >= args.t:
                for name, (x, y, conf) in fp.keypoints.items():
                    cv2.circle(frame, (int(x * w), int(y * h)), 6, (0, 0, 255), -1)
                    cv2.putText(frame, f"{name} {conf:.2f}",
                                (int(x * w) + 8, int(y * h)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
                break

    out = args.out or str(Path(args.video).with_suffix("")) + ".roi_preview.jpg"
    cv2.imwrite(out, frame)
    print(f"wrote {out}  (frame at t={args.t}s, {w}x{h})")


if __name__ == "__main__":
    main()
