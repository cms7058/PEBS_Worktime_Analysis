"""SQLite storage for the process library and analysis results.

Schema:
    processes  one row per 工序 (config package: ROIs + step rules as YAML)
    batches    one row per 采集批次 (an uploaded video analyzed against a process)
    cycles     one row per detected work cycle (the unit of all statistics)

Plain sqlite3 with JSON columns keeps the MVP dependency-free; the DAL below
is the only place that touches SQL, so swapping to Postgres later is local.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

DB_PATH = Path(__file__).parent.parent / "data" / "pebs.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS processes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    config_yaml TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    process_id INTEGER NOT NULL REFERENCES processes(id) ON DELETE CASCADE,
    video_path TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    backend TEXT NOT NULL DEFAULT 'pose',
    sample_fps REAL NOT NULL DEFAULT 10.0,
    status TEXT NOT NULL DEFAULT 'pending',
    error TEXT,
    summary_json TEXT,
    created_at TEXT NOT NULL,
    finished_at TEXT
);
CREATE TABLE IF NOT EXISTS cycles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
    cycle_idx INTEGER NOT NULL,
    t_start REAL NOT NULL,
    t_end REAL,
    duration REAL,
    status TEXT NOT NULL,
    steps_json TEXT NOT NULL,
    anomalies_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_batches_process ON batches(process_id);
CREATE INDEX IF NOT EXISTS idx_cycles_batch ON cycles(batch_id);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(db_path: Optional[Path] = None) -> sqlite3.Connection:
    # Resolve DB_PATH at call time so tests can monkeypatch it.
    db_path = Path(db_path) if db_path else DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: FastAPI may hand the per-request connection to
    # a worker thread; each request still uses its own connection.
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def _row(r: Optional[sqlite3.Row]) -> Optional[dict]:
    if r is None:
        return None
    d = dict(r)
    for key in ("summary_json", "steps_json", "anomalies_json"):
        if key in d:
            d[key.removesuffix("_json")] = json.loads(d.pop(key)) if d[key] else None
    return d


# -- processes ---------------------------------------------------------------

def create_process(conn, name: str, description: str, config_yaml: str) -> dict:
    t = now()
    cur = conn.execute(
        "INSERT INTO processes (name, description, config_yaml, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (name, description, config_yaml, t, t),
    )
    conn.commit()
    return get_process(conn, cur.lastrowid)


def get_process(conn, process_id: int) -> Optional[dict]:
    return _row(conn.execute(
        "SELECT * FROM processes WHERE id = ?", (process_id,)).fetchone())


def list_processes(conn) -> list[dict]:
    return [_row(r) for r in conn.execute(
        "SELECT * FROM processes ORDER BY id").fetchall()]


def update_process(conn, process_id: int, **fields: Any) -> Optional[dict]:
    allowed = {k: v for k, v in fields.items()
               if k in ("name", "description", "config_yaml") and v is not None}
    if allowed:
        sets = ", ".join(f"{k} = ?" for k in allowed)
        conn.execute(
            f"UPDATE processes SET {sets}, updated_at = ? WHERE id = ?",
            (*allowed.values(), now(), process_id),
        )
        conn.commit()
    return get_process(conn, process_id)


def delete_process(conn, process_id: int) -> bool:
    cur = conn.execute("DELETE FROM processes WHERE id = ?", (process_id,))
    conn.commit()
    return cur.rowcount > 0


# -- batches -----------------------------------------------------------------

def create_batch(conn, process_id: int, video_path: str, label: str,
                 backend: str, sample_fps: float) -> dict:
    cur = conn.execute(
        "INSERT INTO batches (process_id, video_path, label, backend, sample_fps,"
        " status, created_at) VALUES (?, ?, ?, ?, ?, 'pending', ?)",
        (process_id, video_path, label, backend, sample_fps, now()),
    )
    conn.commit()
    return get_batch(conn, cur.lastrowid)


def get_batch(conn, batch_id: int) -> Optional[dict]:
    return _row(conn.execute(
        "SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone())


def list_batches(conn, process_id: Optional[int] = None) -> list[dict]:
    if process_id is None:
        rows = conn.execute("SELECT * FROM batches ORDER BY id").fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM batches WHERE process_id = ? ORDER BY id",
            (process_id,)).fetchall()
    return [_row(r) for r in rows]


def set_batch_status(conn, batch_id: int, status: str,
                     error: Optional[str] = None,
                     summary: Optional[dict] = None) -> None:
    conn.execute(
        "UPDATE batches SET status = ?, error = ?, summary_json = ?,"
        " finished_at = CASE WHEN ? IN ('done', 'failed') THEN ? ELSE finished_at END"
        " WHERE id = ?",
        (status, error, json.dumps(summary, ensure_ascii=False) if summary else None,
         status, now(), batch_id),
    )
    conn.commit()


# -- cycles ------------------------------------------------------------------

def insert_cycles(conn, batch_id: int, cycles: list[dict]) -> None:
    conn.executemany(
        "INSERT INTO cycles (batch_id, cycle_idx, t_start, t_end, duration,"
        " status, steps_json, anomalies_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [(batch_id, c["cycle_idx"], c["t_start"], c["t_end"], c["duration"],
          c["status"], json.dumps(c["steps"], ensure_ascii=False),
          json.dumps(c["anomalies"], ensure_ascii=False)) for c in cycles],
    )
    conn.commit()


def list_cycles(conn, batch_id: Optional[int] = None,
                process_id: Optional[int] = None,
                status: Optional[str] = None) -> list[dict]:
    sql = ("SELECT c.*, b.process_id, b.label AS batch_label FROM cycles c"
           " JOIN batches b ON b.id = c.batch_id WHERE 1=1")
    args: list = []
    if batch_id is not None:
        sql += " AND c.batch_id = ?"
        args.append(batch_id)
    if process_id is not None:
        sql += " AND b.process_id = ?"
        args.append(process_id)
    if status is not None:
        sql += " AND c.status = ?"
        args.append(status)
    sql += " ORDER BY c.batch_id, c.cycle_idx"
    return [_row(r) for r in conn.execute(sql, args).fetchall()]
