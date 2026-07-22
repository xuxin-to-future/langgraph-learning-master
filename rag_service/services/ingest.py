"""文档入库：落盘、解析、切片、写库；删除与重索引。"""

from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rag_service.config.settings import get_settings
from rag_service.services import kb as kb_service
from rag_service.services.chunking import split_text
from rag_service.services.embedding import embed_texts, pack_embedding
from rag_service.services.fts import delete_doc_fts, upsert_chunk_fts
from rag_service.storage.db import connect, init_db


class IngestError(ValueError):
    """可映射为 4xx 的入库错误。"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_document(doc_id: str, *, db_path: Path | None = None) -> dict[str, Any] | None:
    if not doc_id or not str(doc_id).strip():
        return None
    init_db(db_path)
    with connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT doc_id, kb_id, title, source_name, file_path, status, error,
                   chunk_count, created_at, updated_at
            FROM documents
            WHERE doc_id = ?
            """,
            (doc_id.strip(),),
        ).fetchone()
    return _row_to_doc(row) if row else None


def list_documents(kb_id: str, *, db_path: Path | None = None) -> list[dict[str, Any]]:
    init_db(db_path)
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT doc_id, kb_id, title, source_name, file_path, status, error,
                   chunk_count, created_at, updated_at
            FROM documents
            WHERE kb_id = ?
            ORDER BY created_at DESC
            """,
            (kb_id,),
        ).fetchall()
    return [_row_to_doc(r) for r in rows]


def ingest_upload(
    *,
    kb_id: str,
    filename: str,
    content: bytes,
    title: str | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """同步入库：校验 → 落盘 → 切片 → ready/failed。"""
    settings = get_settings()
    init_db(db_path)
    # 首次访问时确保 default 知识库存在（与 list KB 行为一致）
    kb_service.ensure_default_kb(db_path=db_path)

    kb = kb_service.get_kb(kb_id, db_path=db_path)
    if kb is None:
        raise IngestError(f"知识库不存在: {kb_id}")

    name = Path(filename or "").name
    if not name:
        raise IngestError("文件名无效")

    suffix = Path(name).suffix.lower()
    if suffix not in settings.allowed_extensions:
        allowed = ", ".join(sorted(settings.allowed_extensions))
        raise IngestError(f"不支持的文件类型: {suffix or '(无扩展名)'}，允许: {allowed}")

    if len(content) > settings.max_upload_bytes:
        raise IngestError(
            f"文件过大: {len(content)} bytes，上限 {settings.max_upload_bytes}"
        )
    if len(content) == 0:
        raise IngestError("文件内容为空")

    doc_id = f"doc_{uuid.uuid4().hex[:12]}"
    doc_title = (title or "").strip() or Path(name).stem
    created = _now()

    dest_dir = settings.files_dir / kb_id / doc_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / name
    dest_path.write_bytes(content)

    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO documents (
                doc_id, kb_id, title, source_name, file_path, status, error,
                chunk_count, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'pending', NULL, 0, ?, ?)
            """,
            (doc_id, kb_id, doc_title, name, str(dest_path), created, created),
        )
        conn.commit()

    try:
        text = _decode_text(content)
        pieces = split_text(
            text,
            max_tokens=settings.chunk_token_num,
            overlap_percent=settings.chunk_overlap_percent,
            max_chars=settings.chunk_max_chars,
        )
        if not pieces:
            raise IngestError("未能从文件中解析出有效文本切片")

        chunk_rows = _replace_chunks(
            doc_id=doc_id,
            kb_id=kb_id,
            source_name=name,
            pieces=pieces,
            db_path=db_path,
        )
        # 可选向量：有 Key 且接口可用时写入；失败不影响 ready
        _maybe_embed_chunks(chunk_rows, db_path=db_path)
    except Exception as exc:  # noqa: BLE001
        err = str(exc)
        with connect(db_path) as conn:
            conn.execute(
                """
                UPDATE documents
                SET status = 'failed', error = ?, updated_at = ?
                WHERE doc_id = ?
                """,
                (err[:1000], _now(), doc_id),
            )
            conn.commit()
        if isinstance(exc, IngestError):
            raise
        raise IngestError(f"解析失败: {err}") from exc

    row = get_document(doc_id, db_path=db_path)
    assert row is not None
    return row


def delete_document(doc_id: str, *, db_path: Path | None = None) -> bool:
    """删除文档元数据、chunks、FTS 与落盘文件。不存在则返回 False。"""
    doc = get_document(doc_id, db_path=db_path)
    if doc is None:
        return False

    init_db(db_path)
    with connect(db_path) as conn:
        delete_doc_fts(conn, doc_id)
        conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
        conn.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))
        conn.commit()

    file_path = Path(doc.get("file_path") or "")
    if file_path.is_file():
        try:
            file_path.unlink()
        except OSError:
            pass
    # 文件目录：files/{kb_id}/{doc_id}/
    doc_dir = file_path.parent if file_path.name else None
    settings = get_settings()
    expected = settings.files_dir / doc["kb_id"] / doc_id
    for folder in {doc_dir, expected}:
        if folder is None:
            continue
        try:
            if folder.is_dir() and folder.resolve() != settings.files_dir.resolve():
                shutil.rmtree(folder, ignore_errors=True)
        except OSError:
            pass
    return True


def reindex_document(doc_id: str, *, db_path: Path | None = None) -> dict[str, Any]:
    """按磁盘文件重新解析切片与索引。"""
    settings = get_settings()
    doc = get_document(doc_id, db_path=db_path)
    if doc is None:
        raise IngestError(f"文档不存在: {doc_id}")

    file_path = Path(doc.get("file_path") or "")
    if not file_path.is_file():
        raise IngestError(f"源文件不存在: {file_path}")

    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE documents
            SET status = 'pending', error = NULL, updated_at = ?
            WHERE doc_id = ?
            """,
            (_now(), doc_id),
        )
        conn.commit()

    try:
        content = file_path.read_bytes()
        text = _decode_text(content)
        pieces = split_text(
            text,
            max_tokens=settings.chunk_token_num,
            overlap_percent=settings.chunk_overlap_percent,
            max_chars=settings.chunk_max_chars,
        )
        if not pieces:
            raise IngestError("未能从文件中解析出有效文本切片")

        source_name = doc.get("source_name") or file_path.name
        chunk_rows = _replace_chunks(
            doc_id=doc_id,
            kb_id=doc["kb_id"],
            source_name=source_name,
            pieces=pieces,
            db_path=db_path,
        )
        _maybe_embed_chunks(chunk_rows, db_path=db_path)
    except Exception as exc:  # noqa: BLE001
        err = str(exc)
        with connect(db_path) as conn:
            conn.execute(
                """
                UPDATE documents
                SET status = 'failed', error = ?, updated_at = ?
                WHERE doc_id = ?
                """,
                (err[:1000], _now(), doc_id),
            )
            conn.commit()
        if isinstance(exc, IngestError):
            raise
        raise IngestError(f"重索引失败: {err}") from exc

    row = get_document(doc_id, db_path=db_path)
    assert row is not None
    return row


def _replace_chunks(
    *,
    doc_id: str,
    kb_id: str,
    source_name: str,
    pieces: list[Any],
    db_path: Path | None,
) -> list[tuple[str, str]]:
    """删除旧 chunks/FTS 后写入新切片，并标记 ready。"""
    chunk_rows: list[tuple[str, str]] = []
    with connect(db_path) as conn:
        delete_doc_fts(conn, doc_id)
        conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
        for piece in pieces:
            chunk_id = f"chk_{uuid.uuid4().hex[:12]}"
            conn.execute(
                """
                INSERT INTO chunks (
                    chunk_id, doc_id, kb_id, text, source, heading,
                    position, embedding, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?)
                """,
                (
                    chunk_id,
                    doc_id,
                    kb_id,
                    piece.text,
                    source_name,
                    piece.heading,
                    piece.position,
                    _now(),
                ),
            )
            upsert_chunk_fts(
                conn,
                chunk_id=chunk_id,
                kb_id=kb_id,
                text=piece.text,
            )
            chunk_rows.append((chunk_id, piece.text))
        conn.execute(
            """
            UPDATE documents
            SET status = 'ready', error = NULL, chunk_count = ?, updated_at = ?
            WHERE doc_id = ?
            """,
            (len(pieces), _now(), doc_id),
        )
        conn.commit()
    return chunk_rows


def _maybe_embed_chunks(
    chunk_rows: list[tuple[str, str]],
    *,
    db_path: Path | None = None,
) -> None:
    if not chunk_rows:
        return
    texts = [t for _, t in chunk_rows]
    vectors = embed_texts(texts)
    if not vectors:
        return
    with connect(db_path) as conn:
        for (chunk_id, _), vec in zip(chunk_rows, vectors, strict=True):
            conn.execute(
                "UPDATE chunks SET embedding = ? WHERE chunk_id = ?",
                (pack_embedding(vec), chunk_id),
            )
        conn.commit()


def _decode_text(content: bytes) -> str:
    for enc in ("utf-8", "utf-8-sig", "gbk", "latin-1"):
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    raise IngestError("无法解码文件文本（请使用 UTF-8）")


def _row_to_doc(row: Any) -> dict[str, Any]:
    return {
        "doc_id": row["doc_id"],
        "kb_id": row["kb_id"],
        "title": row["title"],
        "source_name": row["source_name"],
        "file_path": row["file_path"],
        "status": row["status"],
        "error": row["error"],
        "chunk_count": row["chunk_count"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
