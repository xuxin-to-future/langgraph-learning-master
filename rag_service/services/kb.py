"""知识库领域服务。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rag_service.config.settings import get_settings
from rag_service.storage.db import connect, init_db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_default_kb(db_path: Path | None = None) -> dict[str, Any]:
    """确保 default 知识库存在，返回其记录。"""
    settings = get_settings()
    init_db(db_path)
    existing = get_kb(settings.default_kb_id, db_path=db_path)
    if existing is not None:
        return existing
    return create_kb(
        name=settings.default_kb_name,
        description="默认知识库",
        kb_id=settings.default_kb_id,
        db_path=db_path,
    )


def create_kb(
    *,
    name: str,
    description: str = "",
    kb_id: str | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    name = (name or "").strip()
    if not name:
        raise ValueError("name is required")

    init_db(db_path)
    kid = (kb_id or f"kb_{uuid.uuid4().hex[:10]}").strip()
    created_at = _now()

    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO knowledge_bases (kb_id, name, description, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (kid, name, description or "", created_at),
        )
        conn.commit()

    row = get_kb(kid, db_path=db_path)
    assert row is not None
    return row


def list_kbs(*, db_path: Path | None = None) -> list[dict[str, Any]]:
    init_db(db_path)
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT kb_id, name, description, created_at
            FROM knowledge_bases
            ORDER BY created_at ASC
            """
        ).fetchall()
    return [_row_to_kb(r) for r in rows]


def get_kb(kb_id: str, *, db_path: Path | None = None) -> dict[str, Any] | None:
    if not kb_id or not kb_id.strip():
        return None
    init_db(db_path)
    with connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT kb_id, name, description, created_at
            FROM knowledge_bases
            WHERE kb_id = ?
            """,
            (kb_id.strip(),),
        ).fetchone()
    return _row_to_kb(row) if row else None


def _row_to_kb(row: Any) -> dict[str, Any]:
    return {
        "kb_id": row["kb_id"],
        "name": row["name"],
        "description": row["description"],
        "created_at": row["created_at"],
    }
