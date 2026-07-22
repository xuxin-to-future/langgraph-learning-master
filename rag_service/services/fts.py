"""FTS5 关键词索引：入库时同步，检索时 MATCH。"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from rag_service.storage.db import connect, init_db

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_LATIN_RE = re.compile(r"[A-Za-z0-9_]+")
_STOP_CJK = frozenset("的了是在有和与或什么怎么吗呢啊呀么")


def to_fts_document(text: str) -> str:
    """把文本拆成 FTS 友好的空格分词（汉字单字 + 英文单词）。"""
    tokens: list[str] = []
    buf: list[str] = []
    for ch in text or "":
        if _CJK_RE.match(ch):
            if buf:
                tokens.append("".join(buf).lower())
                buf = []
            tokens.append(ch)
        elif ch.isalnum() or ch == "_":
            buf.append(ch)
        else:
            if buf:
                tokens.append("".join(buf).lower())
                buf = []
    if buf:
        tokens.append("".join(buf).lower())
    return " ".join(tokens)


def extract_query_terms(query: str) -> list[str]:
    """抽取检索词：CJK bigram + 单字，英文单词。"""
    q = (query or "").strip()
    if not q:
        return []

    terms: list[str] = []
    for m in _LATIN_RE.finditer(q):
        w = m.group(0).lower()
        if len(w) >= 2:
            terms.append(w)

    cjk = "".join(_CJK_RE.findall(q))
    if len(cjk) >= 2:
        for i in range(len(cjk) - 1):
            terms.append(cjk[i : i + 2])
    for ch in cjk:
        if ch not in _STOP_CJK:
            terms.append(ch)

    # 去重保序
    seen: set[str] = set()
    out: list[str] = []
    for t in terms:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def build_fts_match_query(terms: list[str]) -> str | None:
    """构造 FTS5 MATCH 表达式；词过多时截断。"""
    cleaned: list[str] = []
    for t in terms[:32]:
        safe = re.sub(r'[^\w\u4e00-\u9fff]+', "", t, flags=re.UNICODE)
        if not safe:
            continue
        cleaned.append(f'"{safe}"')
    if not cleaned:
        return None
    return " OR ".join(cleaned)


def ensure_fts(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            chunk_id UNINDEXED,
            kb_id UNINDEXED,
            body,
            tokenize = 'unicode61'
        )
        """
    )


def upsert_chunk_fts(
    conn: sqlite3.Connection,
    *,
    chunk_id: str,
    kb_id: str,
    text: str,
) -> None:
    ensure_fts(conn)
    conn.execute("DELETE FROM chunks_fts WHERE chunk_id = ?", (chunk_id,))
    conn.execute(
        "INSERT INTO chunks_fts (chunk_id, kb_id, body) VALUES (?, ?, ?)",
        (chunk_id, kb_id, to_fts_document(text)),
    )


def delete_doc_fts(conn: sqlite3.Connection, doc_id: str) -> None:
    ensure_fts(conn)
    rows = conn.execute(
        "SELECT chunk_id FROM chunks WHERE doc_id = ?",
        (doc_id,),
    ).fetchall()
    for row in rows:
        conn.execute("DELETE FROM chunks_fts WHERE chunk_id = ?", (row["chunk_id"],))


def index_chunks_for_doc(
    *,
    doc_id: str,
    db_path: Path | None = None,
) -> int:
    """按 documents 下已有 chunks 重建 FTS 行，返回索引条数。"""
    init_db(db_path)
    with connect(db_path) as conn:
        ensure_fts(conn)
        rows = conn.execute(
            "SELECT chunk_id, kb_id, text FROM chunks WHERE doc_id = ?",
            (doc_id,),
        ).fetchall()
        for row in rows:
            upsert_chunk_fts(
                conn,
                chunk_id=row["chunk_id"],
                kb_id=row["kb_id"],
                text=row["text"],
            )
        conn.commit()
    return len(rows)
