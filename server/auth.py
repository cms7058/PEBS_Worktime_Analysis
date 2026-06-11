"""用户与会话：PBKDF2 密码哈希 + 随机令牌 + sqlite 存储.

零外部依赖（hashlib + secrets）。会话令牌存数据库，前端放 localStorage。
首次启动若无用户自动创建 admin/admin123，登录后强烈建议修改。
"""
from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

SESSION_TTL_DAYS = 7
PBKDF2_ITERS = 120_000

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(d: datetime) -> str:
    return d.isoformat(timespec="seconds")


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERS)
    return salt.hex() + "$" + dk.hex()


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, dk_hex = stored.split("$", 1)
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), PBKDF2_ITERS)
        return secrets.compare_digest(dk.hex(), dk_hex)
    except (ValueError, AttributeError):
        return False


def _user_row(row) -> Optional[dict]:
    if row is None:
        return None
    return {"id": row["id"], "username": row["username"],
            "role": row["role"], "created_at": row["created_at"]}


def init(conn) -> None:
    conn.executescript(SCHEMA)
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        create_user(conn, "admin", "admin123", role="admin")
        print("[PEBS] 已创建默认管理员账号：admin / admin123，登录后请立即修改密码")


def create_user(conn, username: str, password: str, role: str = "user") -> dict:
    if role not in ("admin", "user"):
        raise ValueError("role must be 'admin' or 'user'")
    cur = conn.execute(
        "INSERT INTO users (username, password_hash, role, created_at)"
        " VALUES (?, ?, ?, ?)",
        (username, hash_password(password), role, _iso(_now())),
    )
    conn.commit()
    return _user_row(conn.execute(
        "SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone())


def list_users(conn) -> list[dict]:
    conn.executescript(SCHEMA)
    return [_user_row(r) for r in conn.execute(
        "SELECT * FROM users ORDER BY id").fetchall()]


def get_user(conn, user_id: int) -> Optional[dict]:
    return _user_row(conn.execute(
        "SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())


def delete_user(conn, user_id: int) -> bool:
    cur = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    return cur.rowcount > 0


def set_password(conn, user_id: int, password: str) -> None:
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                 (hash_password(password), user_id))
    conn.commit()


def set_role(conn, user_id: int, role: str) -> None:
    if role not in ("admin", "user"):
        raise ValueError("role must be 'admin' or 'user'")
    conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
    conn.commit()


def login(conn, username: str, password: str) -> Optional[dict]:
    conn.executescript(SCHEMA)
    row = conn.execute("SELECT * FROM users WHERE username = ?",
                       (username,)).fetchone()
    if row is None or not verify_password(password, row["password_hash"]):
        return None
    token = secrets.token_urlsafe(32)
    now = _now()
    conn.execute(
        "INSERT INTO sessions (token, user_id, created_at, expires_at)"
        " VALUES (?, ?, ?, ?)",
        (token, row["id"], _iso(now),
         _iso(now + timedelta(days=SESSION_TTL_DAYS))),
    )
    conn.commit()
    return {"token": token, "user": _user_row(row)}


def logout(conn, token: str) -> None:
    if token:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()


def check_token(conn, token: str) -> Optional[dict]:
    if not token:
        return None
    try:
        conn.executescript(SCHEMA)
    except sqlite3.OperationalError:
        return None
    row = conn.execute(
        "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id"
        " WHERE s.token = ? AND s.expires_at > ?",
        (token, _iso(_now())),
    ).fetchone()
    return _user_row(row)
