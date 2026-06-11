"""Perception layer: video -> per-frame keypoint stream (JSONL).

Uses MediaPipe Pose (CPU-friendly) and emits normalized keypoints for the
body landmarks relevant to manual-work analysis. Designed to be swappable:
any backend that yields FramePerception objects can replace it (e.g. RTMPose
on a GPU box) without touching the event/rule layers.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterator, Optional

import cv2

from .schemas import FramePerception

# MediaPipe Pose landmark indices we keep. Wrists are the workhorses for
# ROI-based work-step rules; shoulders/nose give body presence and posture.
LANDMARKS = {
    0: "nose",
    11: "left_shoulder",
    12: "right_shoulder",
    13: "left_elbow",
    14: "right_elbow",
    15: "left_wrist",
    16: "right_wrist",
}


MODELS_DIR = Path(__file__).parent.parent / "models"
POSE_MODEL = MODELS_DIR / "pose_landmarker_lite.task"
HAND_MODEL = MODELS_DIR / "hand_landmarker.task"

# Hand Landmarker indices: 0 = wrist, 8 = index fingertip
HAND_LANDMARKS = {0: "wrist", 8: "index_tip"}


def _frames(cap, video_fps, step):
    frame_idx = -1
    while True:
        ok, frame = cap.read()
        if not ok:
            return
        frame_idx += 1
        if frame_idx % step:
            continue
        yield frame_idx, frame_idx / video_fps, frame


def analyze_video(
    video_path: str | Path,
    sample_fps: Optional[float] = None,
    min_confidence: float = 0.5,
    backend: str = "pose",
) -> Iterator[FramePerception]:
    """Yield FramePerception for each (sampled) frame of the video.

    backend: "pose" for full/upper-body camera views, "hands" for close-up
    workstation views where only hands/arms are visible (Pose needs a body
    in frame and fails on those). Both emit `left_wrist`/`right_wrist` so
    process configs work unchanged; "hands" adds `*_index_tip`.
    Uses the MediaPipe Tasks API (legacy solutions were removed in 0.10.x).
    """
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions
    from mediapipe.tasks.python import vision

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise FileNotFoundError(f"Cannot open video: {video_path}")
    video_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = 1 if not sample_fps else max(1, round(video_fps / sample_fps))

    if backend == "pose":
        landmarker = vision.PoseLandmarker.create_from_options(
            vision.PoseLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=str(POSE_MODEL)),
                running_mode=vision.RunningMode.VIDEO,
                min_pose_detection_confidence=min_confidence,
                min_tracking_confidence=min_confidence,
            )
        )
    elif backend == "hands":
        landmarker = vision.HandLandmarker.create_from_options(
            vision.HandLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=str(HAND_MODEL)),
                running_mode=vision.RunningMode.VIDEO,
                num_hands=2,
                min_hand_detection_confidence=min_confidence,
                min_tracking_confidence=min_confidence,
            )
        )
    else:
        raise ValueError(f"unknown backend: {backend!r} (use 'pose' or 'hands')")

    try:
        for frame_idx, t, frame in _frames(cap, video_fps, step):
            mp_image = mp.Image(
                image_format=mp.ImageFormat.SRGB,
                data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB),
            )
            result = landmarker.detect_for_video(mp_image, int(t * 1000))
            keypoints: dict[str, list] = {}
            if backend == "pose":
                detected = bool(result.pose_landmarks)
                if detected:
                    landmarks = result.pose_landmarks[0]   # single-worker workstation
                    for idx, name in LANDMARKS.items():
                        lm = landmarks[idx]
                        keypoints[name] = [
                            round(lm.x, 5), round(lm.y, 5),
                            round(lm.visibility if lm.visibility is not None else 1.0, 4),
                        ]
            else:
                detected = bool(result.hand_landmarks)
                for hand_lms, handedness in zip(result.hand_landmarks,
                                                result.handedness):
                    # MediaPipe handedness is mirrored for selfie views; for a
                    # fixed top-down workstation camera the label is reliable.
                    side = handedness[0].category_name.lower()   # left | right
                    score = handedness[0].score
                    for idx, suffix in HAND_LANDMARKS.items():
                        lm = hand_lms[idx]
                        keypoints[f"{side}_{suffix}"] = [
                            round(lm.x, 5), round(lm.y, 5), round(score, 4),
                        ]
            yield FramePerception(
                frame_idx=frame_idx, t=round(t, 4),
                keypoints=keypoints, person_detected=detected,
            )
    finally:
        landmarker.close()
        cap.release()


def run(video_path: str, output_path: str, sample_fps: Optional[float] = None,
        backend: str = "pose") -> int:
    """Analyze a video and write the keypoint stream to a JSONL file."""
    n = 0
    with open(output_path, "w") as f:
        for fp in analyze_video(video_path, sample_fps=sample_fps, backend=backend):
            f.write(fp.to_json() + "\n")
            n += 1
    return n


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: python -m pipeline.perception <video> <out.jsonl> [sample_fps] [backend]")
        sys.exit(1)
    fps = float(sys.argv[3]) if len(sys.argv) > 3 else None
    backend = sys.argv[4] if len(sys.argv) > 4 else "pose"
    count = run(sys.argv[1], sys.argv[2], fps, backend)
    print(f"wrote {count} frames -> {sys.argv[2]}")
