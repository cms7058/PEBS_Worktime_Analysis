"""Background analysis worker: run the pipeline for a batch and persist results.

Runs inside FastAPI's BackgroundTasks (single worker is fine for the MVP;
swap for a real task queue when concurrent batches matter). Each run opens
its own DB connection — sqlite3 connections are not thread-safe.
"""
from __future__ import annotations

import dataclasses
import tempfile
from pathlib import Path

import yaml

from pipeline.events import EventDetector
from pipeline.perception import analyze_video
from pipeline.rules import ProcessConfig, RuleEngine, summarize

from . import db


def validate_config_yaml(config_yaml: str) -> ProcessConfig:
    """Parse a process config from a YAML string, raising ValueError on problems."""
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write(config_yaml)
            tmp = f.name
        cfg = ProcessConfig.from_yaml(tmp)
    except (yaml.YAMLError, KeyError, TypeError) as e:
        raise ValueError(f"invalid process config: {e}") from e
    finally:
        Path(tmp).unlink(missing_ok=True)
    if not cfg.steps:
        raise ValueError("invalid process config: at least one step is required")
    return cfg


def run_batch(batch_id: int) -> None:
    conn = db.connect()
    try:
        batch = db.get_batch(conn, batch_id)
        if batch is None:
            return
        db.set_batch_status(conn, batch_id, "running")
        process = db.get_process(conn, batch["process_id"])
        cfg = validate_config_yaml(process["config_yaml"])

        frames = analyze_video(
            batch["video_path"],
            sample_fps=batch["sample_fps"],
            backend=batch["backend"],
        )
        detector = EventDetector(rois=cfg.rois, keypoints=cfg.keypoints)
        events = sorted(detector.process(frames), key=lambda e: (e.t, e.frame_idx))
        cycles = RuleEngine(cfg).run(iter(events))

        db.insert_cycles(conn, batch_id, [dataclasses.asdict(c) for c in cycles])
        db.set_batch_status(conn, batch_id, "done", summary=summarize(cycles))
    except Exception as e:   # persist the failure; a silent dead batch is worse
        db.set_batch_status(conn, batch_id, "failed", error=f"{type(e).__name__}: {e}")
    finally:
        conn.close()
