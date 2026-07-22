"""工单存储服务（SQLite）。"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from customer_service.config.settings import get_settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
    ticket_id   TEXT PRIMARY KEY,
    subject     TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'open',
    session_id  TEXT,
    created_at  TEXT NOT NULL
);
"""


def _db_path(db_path: Path | None = None) -> Path:
    return Path(db_path) if db_path is not None else get_settings().tickets_db_path


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = _db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path | None = None) -> Path:
    """初始化表结构，返回数据库文件路径。"""
    path = _db_path(db_path)
    with _connect(path) as conn:
        conn.executescript(_SCHEMA)
        conn.commit()
    return path


def create_ticket(
    *,
    subject: str,
    description: str = "",
    session_id: str | None = None,
    db_path: Path | None = None,
) -> str:
    """创建工单，返回 ticket_id。写库失败时抛出异常，不伪造 id。"""
    subject = (subject or "").strip()
    if not subject:
        raise ValueError("subject is required")

    ticket_id = f"TK-{uuid.uuid4().hex[:10].upper()}"
    created_at = datetime.now(timezone.utc).isoformat()

    path = init_db(db_path)
    try:
        with _connect(path) as conn:
            conn.execute(
                """
                INSERT INTO tickets (ticket_id, subject, description, status, session_id, created_at)
                VALUES (?, ?, ?, 'open', ?, ?)
                """,
                (ticket_id, subject, description or "", session_id, created_at),
            )
            conn.commit()
    except sqlite3.Error as exc:
        raise RuntimeError(f"failed to create ticket: {exc}") from exc

    return ticket_id


def get_ticket(
    ticket_id: str,
    *,
    db_path: Path | None = None,
) -> dict[str, Any] | None:
    """按 id 查询工单；不存在返回 None。"""
    if not ticket_id or not ticket_id.strip():
        return None

    path = init_db(db_path)
    with _connect(path) as conn:
        row = conn.execute(
            """
            SELECT ticket_id, subject, description, status, session_id, created_at
            FROM tickets
            WHERE ticket_id = ?
            """,
            (ticket_id.strip(),),
        ).fetchone()

    if row is None:
        return None

    return {
        "ticket_id": row["ticket_id"],
        "subject": row["subject"],
        "description": row["description"],
        "status": row["status"],
        "session_id": row["session_id"],
        "created_at": row["created_at"],
    }
