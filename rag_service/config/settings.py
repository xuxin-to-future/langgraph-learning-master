"""环境与路径配置。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parent

DEFAULT_ALLOWED_EXTENSIONS = frozenset({".md", ".txt"})


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_path(name: str, default: Path) -> Path:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return Path(raw).expanduser()


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default


def _parse_extensions(raw: str | None) -> frozenset[str]:
    if not raw or not raw.strip():
        return DEFAULT_ALLOWED_EXTENSIONS
    items = []
    for part in raw.split(","):
        p = part.strip().lower()
        if not p:
            continue
        if not p.startswith("."):
            p = f".{p}"
        items.append(p)
    return frozenset(items) if items else DEFAULT_ALLOWED_EXTENSIONS


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw.strip())
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    """RAG 运行时配置。"""

    data_dir: Path
    db_path: Path
    files_dir: Path
    max_upload_bytes: int
    allowed_extensions: frozenset[str]
    default_kb_name: str
    default_kb_id: str
    # Chat / rerank（可与 embedding 分离，如 DeepSeek 聊天 + 硅基流动向量）
    openai_api_key: str | None
    openai_base_url: str | None
    # Embedding（独立 Key / Base URL）
    embedding_api_key: str | None
    embedding_base_url: str | None
    embedding_model: str
    # Rerank（默认复用 embedding 的硅基流动 Key/Base）
    rerank_api_key: str | None
    rerank_base_url: str | None
    rerank_model: str
    # 混合召回：对齐 RAGFlow hybrid_similarity（默认向量 0.7 / 词项 0.3）
    vector_similarity_weight: float
    chunk_token_num: int
    chunk_overlap_percent: int
    chunk_max_chars: int  # deprecated 硬切兜底；主计量为 chunk_token_num

    @property
    def has_openai_key(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def has_embedding_key(self) -> bool:
        return bool(self.embedding_api_key)

    @property
    def has_rerank_key(self) -> bool:
        return bool(self.rerank_api_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """加载并缓存配置；测试可 `get_settings.cache_clear()`。"""
    load_dotenv(REPO_ROOT / ".env")

    data_dir = _env_path("RAG_DATA_DIR", REPO_ROOT / "data" / "rag")
    db_path = _env_path("RAG_DB_PATH", data_dir / "rag.db")
    files_dir = _env_path("RAG_FILES_DIR", data_dir / "files")

    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("RAG_OPENAI_API_KEY")
    if api_key is not None:
        api_key = api_key.strip() or None

    base_url = (os.getenv("OPENAI_BASE_URL") or os.getenv("RAG_OPENAI_BASE_URL") or "").strip() or None

    emb_key = (
        os.getenv("RAG_EMBEDDING_API_KEY")
        or os.getenv("SILICONFLOW_API_KEY")
        or api_key
    )
    if emb_key is not None:
        emb_key = emb_key.strip() or None

    emb_base = (
        os.getenv("RAG_EMBEDDING_BASE_URL")
        or os.getenv("SILICONFLOW_BASE_URL")
        or ""
    ).strip() or None
    # 未单独配置 embedding base 时：若聊天 base 不是 DeepSeek，可复用；否则不回退（避免 404）
    if emb_base is None and base_url and "deepseek.com" not in base_url.lower():
        emb_base = base_url

    return Settings(
        data_dir=data_dir,
        db_path=db_path,
        files_dir=files_dir,
        max_upload_bytes=_env_int("RAG_MAX_UPLOAD_BYTES", 2 * 1024 * 1024),
        allowed_extensions=_parse_extensions(os.getenv("RAG_ALLOWED_EXTENSIONS")),
        default_kb_name=(os.getenv("RAG_DEFAULT_KB_NAME") or "default").strip() or "default",
        default_kb_id=(os.getenv("RAG_DEFAULT_KB_ID") or "kb_default").strip() or "kb_default",
        openai_api_key=api_key,
        openai_base_url=base_url,
        embedding_api_key=emb_key,
        embedding_base_url=emb_base,
        embedding_model=(
            os.getenv("RAG_EMBEDDING_MODEL")
            or os.getenv("OPENAI_EMBEDDING_MODEL")
            or "BAAI/bge-m3"
        ).strip(),
        rerank_api_key=(
            (os.getenv("RAG_RERANK_API_KEY") or "").strip()
            or emb_key
        ),
        rerank_base_url=(
            (os.getenv("RAG_RERANK_BASE_URL") or "").strip()
            or emb_base
            or "https://api.siliconflow.cn/v1"
        ),
        rerank_model=(
            os.getenv("RAG_RERANK_MODEL") or "BAAI/bge-reranker-v2-m3"
        ).strip(),
        vector_similarity_weight=max(
            0.0,
            min(1.0, _env_float("RAG_VECTOR_SIMILARITY_WEIGHT", 0.7)),
        ),
        chunk_token_num=max(1, _env_int("RAG_CHUNK_TOKEN_NUM", 512)),
        chunk_overlap_percent=max(0, min(90, _env_int("RAG_CHUNK_OVERLAP_PERCENT", 10))),
        chunk_max_chars=_env_int("RAG_CHUNK_MAX_CHARS", 8000),
    )
