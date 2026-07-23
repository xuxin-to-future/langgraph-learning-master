"""工单存储服务（SQLite）。"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from customer_service.config.settings import get_settings

PROBLEM_TYPE_OPTIONS = (
    "业务问题",
    "系统 Bug",
    "个人反馈",
    "功能建议",
    "其他",
)

RATING_LABELS = {
    1: "很差",
    2: "较差",
    3: "一般",
    4: "较好",
    5: "很好",
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
    ticket_id     TEXT PRIMARY KEY,
    subject       TEXT NOT NULL,
    description   TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'open',
    session_id    TEXT,
    created_at    TEXT NOT NULL,
    problem_types TEXT NOT NULL DEFAULT '[]',
    attachments   TEXT NOT NULL DEFAULT '[]',
    rating        INTEGER,
    reporter      TEXT NOT NULL DEFAULT 'admin'
);
"""

_EXTRA_COLUMNS: tuple[tuple[str, str], ...] = (
    ("problem_types", "TEXT NOT NULL DEFAULT '[]'"),
    ("attachments", "TEXT NOT NULL DEFAULT '[]'"),
    ("rating", "INTEGER"),
    ("reporter", "TEXT NOT NULL DEFAULT 'admin'"),
)


def _db_path(db_path: Path | None = None) -> Path:
    return Path(db_path) if db_path is not None else get_settings().tickets_db_path


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = _db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    existing = {
        row[1] for row in conn.execute("PRAGMA table_info(tickets)").fetchall()
    }
    for name, decl in _EXTRA_COLUMNS:
        if name not in existing:
            conn.execute(f"ALTER TABLE tickets ADD COLUMN {name} {decl}")


def init_db(db_path: Path | None = None) -> Path:
    """初始化表结构，返回数据库文件路径。"""
    path = _db_path(db_path)
    with _connect(path) as conn:
        conn.executescript(_SCHEMA)
        _migrate(conn)
        conn.commit()
    return path


def _subject_from(
    description: str,
    problem_types: list[str] | None = None,
) -> str:
    text = (description or "").strip()
    if text:
        return text if len(text) <= 80 else text[:77] + "..."
    types = [t for t in (problem_types or []) if t]
    if types:
        joined = " / ".join(types)
        return joined if len(joined) <= 80 else joined[:77] + "..."
    return "用户反馈"


def create_ticket(
    *,
    subject: str | None = None,
    description: str = "",
    session_id: str | None = None,
    problem_types: list[str] | None = None,
    attachments: list[str] | None = None,
    rating: int | None = None,
    reporter: str = "admin",
    db_path: Path | None = None,
) -> str:
    """创建工单，返回 ticket_id。写库失败时抛出异常，不伪造 id。"""
    types = list(problem_types or [])
    files = list(attachments or [])
    desc = (description or "").strip()
    subj = (subject or "").strip() or _subject_from(desc, types)
    if not subj:
        raise ValueError("subject is required")

    if rating is not None and rating not in RATING_LABELS:
        raise ValueError("rating must be 1-5")

    ticket_id = f"TK-{uuid.uuid4().hex[:10].upper()}"
    created_at = datetime.now(timezone.utc).isoformat()
    reporter_name = (reporter or "admin").strip() or "admin"

    path = init_db(db_path)
    try:
        with _connect(path) as conn:
            conn.execute(
                """
                INSERT INTO tickets (
                    ticket_id, subject, description, status, session_id, created_at,
                    problem_types, attachments, rating, reporter
                )
                VALUES (?, ?, ?, 'open', ?, ?, ?, ?, ?, ?)
                """,
                (
                    ticket_id,
                    subj,
                    desc,
                    session_id,
                    created_at,
                    json.dumps(types, ensure_ascii=False),
                    json.dumps(files, ensure_ascii=False),
                    rating,
                    reporter_name,
                ),
            )
            conn.commit()
    except sqlite3.Error as exc:
        raise RuntimeError(f"failed to create ticket: {exc}") from exc

    return ticket_id


def _parse_json_list(raw: str | None) -> list[Any]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


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
            SELECT ticket_id, subject, description, status, session_id, created_at,
                   problem_types, attachments, rating, reporter
            FROM tickets
            WHERE ticket_id = ?
            """,
            (ticket_id.strip(),),
        ).fetchone()

    if row is None:
        return None

    keys = set(row.keys())
    return {
        "ticket_id": row["ticket_id"],
        "subject": row["subject"],
        "description": row["description"],
        "status": row["status"],
        "session_id": row["session_id"],
        "created_at": row["created_at"],
        "problem_types": _parse_json_list(
            row["problem_types"] if "problem_types" in keys else "[]"
        ),
        "attachments": _parse_json_list(
            row["attachments"] if "attachments" in keys else "[]"
        ),
        "rating": row["rating"] if "rating" in keys else None,
        "reporter": (row["reporter"] if "reporter" in keys else None) or "admin",
    }
