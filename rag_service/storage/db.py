"""SQLite 元数据存储。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from rag_service.config.settings import get_settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS knowledge_bases (
    kb_id       TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    doc_id       TEXT PRIMARY KEY,
    kb_id        TEXT NOT NULL,
    title        TEXT NOT NULL,
    source_name  TEXT NOT NULL DEFAULT '',
    file_path    TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'pending',
    error        TEXT,
    chunk_count  INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    FOREIGN KEY (kb_id) REFERENCES knowledge_bases(kb_id)
);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id    TEXT PRIMARY KEY,
    doc_id      TEXT NOT NULL,
    kb_id       TEXT NOT NULL,
    text        TEXT NOT NULL,
    source      TEXT NOT NULL DEFAULT '',
    heading     TEXT NOT NULL DEFAULT '',
    position    INTEGER NOT NULL DEFAULT 0,
    embedding   BLOB,
    created_at  TEXT NOT NULL,
    FOREIGN KEY (doc_id) REFERENCES documents(doc_id),
    FOREIGN KEY (kb_id) REFERENCES knowledge_bases(kb_id)
);

CREATE INDEX IF NOT EXISTS idx_documents_kb ON documents(kb_id);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_chunks_kb ON chunks(kb_id);
"""

_FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    chunk_id UNINDEXED,
    kb_id UNINDEXED,
    body,
    tokenize = 'unicode61'
);
"""


def ensure_data_dirs(db_path: Path | None = None, files_dir: Path | None = None) -> None:
    settings = get_settings()
    path = Path(db_path) if db_path is not None else settings.db_path
    files = Path(files_dir) if files_dir is not None else settings.files_dir
    path.parent.mkdir(parents=True, exist_ok=True)
    files.mkdir(parents=True, exist_ok=True)
    settings.data_dir.mkdir(parents=True, exist_ok=True)


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    settings = get_settings()
    path = Path(db_path) if db_path is not None else settings.db_path
    ensure_data_dirs(path)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path | None = None) -> Path:
    """初始化表结构，返回 db 路径。"""
    settings = get_settings()
    path = Path(db_path) if db_path is not None else settings.db_path
    with connect(path) as conn:
        conn.executescript(_SCHEMA)
        conn.executescript(_FTS_SCHEMA)
        conn.commit()
    return path
