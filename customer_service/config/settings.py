"""环境与路径配置。

统一从环境变量 / `.env` 读取，禁止在业务模块散落 `os.getenv`。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parent

# Checkpointer 后端：memory（开发默认）| sqlite（持久演示）
CheckpointerBackend = str  # "memory" | "sqlite"


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


@dataclass(frozen=True)
class Settings:
    """运行时配置。"""

    knowledge_dir: Path
    data_dir: Path
    tickets_db_path: Path
    chroma_dir: Path
    checkpointer_backend: str  # "memory" | "sqlite"
    checkpointer_sqlite_path: Path
    openai_api_key: str | None
    openai_model: str
    openai_base_url: str | None
    # 无 Key 或显式开启时：规则路由 + 关键词检索降级
    allow_offline_fallback: bool
    # RAG：local=本地 knowledge/*.md；http=自研 rag_service
    rag_provider: str  # "local" | "http"
    rag_base_url: str
    rag_kb_id: str
    rag_top_k: int
    rag_rerank: bool
    rag_api_key: str | None
    # 工单附件 OSS（阿里云）
    oss_enabled: bool = True
    oss_access_key_id: str | None = None
    oss_access_key_secret: str | None = None
    oss_endpoint: str = "oss-cn-shanghai.aliyuncs.com"
    oss_bucket: str = ""
    oss_domain: str = ""
    oss_path_prefix: str = "cs/"
    # 会话上下文 token 预算（摘要+最近对话，不含 system/RAG）
    session_context_token_budget: int = 3500

    @property
    def has_openai_key(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def oss_configured(self) -> bool:
        return bool(
            self.oss_enabled
            and self.oss_access_key_id
            and self.oss_access_key_secret
            and self.oss_bucket
            and self.oss_endpoint
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """加载并缓存配置；测试中可调用 `get_settings.cache_clear()` 重置。"""
    load_dotenv(REPO_ROOT / ".env")

    data_dir = _env_path("CUSTOMER_SERVICE_DATA_DIR", REPO_ROOT / "data")
    tickets_db = _env_path("TICKETS_DB_PATH", data_dir / "tickets.db")
    chroma_dir = _env_path("CHROMA_DIR", data_dir / "chroma")
    checkpointer_sqlite = _env_path(
        "CHECKPOINTER_SQLITE_PATH", data_dir / "checkpoints.sqlite"
    )
    backend = (os.getenv("CHECKPOINTER_BACKEND") or "memory").strip().lower()
    if backend not in {"memory", "sqlite"}:
        backend = "memory"

    api_key = os.getenv("OPENAI_API_KEY")
    if api_key is not None:
        api_key = api_key.strip() or None

    rag_provider = (os.getenv("RAG_PROVIDER") or "local").strip().lower()
    if rag_provider not in {"local", "http"}:
        rag_provider = "local"

    rag_api_key = os.getenv("RAG_API_KEY")
    if rag_api_key is not None:
        rag_api_key = rag_api_key.strip() or None

    return Settings(
        knowledge_dir=_env_path(
            "KNOWLEDGE_DIR", PACKAGE_ROOT / "knowledge"
        ),
        data_dir=data_dir,
        tickets_db_path=tickets_db,
        chroma_dir=chroma_dir,
        checkpointer_backend=backend,
        checkpointer_sqlite_path=checkpointer_sqlite,
        openai_api_key=api_key,
        openai_model=(os.getenv("OPENAI_MODEL") or "gpt-4o-mini").strip(),
        openai_base_url=(os.getenv("OPENAI_BASE_URL") or "").strip() or None,
        allow_offline_fallback=_env_bool("ALLOW_OFFLINE_FALLBACK", True),
        rag_provider=rag_provider,
        rag_base_url=(os.getenv("RAG_BASE_URL") or "http://127.0.0.1:8100").strip().rstrip("/"),
        rag_kb_id=(os.getenv("RAG_KB_ID") or "kb_default").strip() or "kb_default",
        rag_top_k=max(1, min(50, _env_int("RAG_TOP_K", 5))),
        rag_rerank=_env_bool("RAG_RERANK", False),
        rag_api_key=rag_api_key,
        oss_enabled=_env_bool("OSS_ENABLED", True),
        oss_access_key_id=(os.getenv("OSS_ACCESS_KEY_ID") or "").strip() or None,
        oss_access_key_secret=(os.getenv("OSS_ACCESS_KEY_SECRET") or "").strip()
        or None,
        oss_endpoint=(
            os.getenv("OSS_ENDPOINT") or "oss-cn-shanghai.aliyuncs.com"
        ).strip(),
        oss_bucket=(os.getenv("OSS_BUCKET") or "").strip(),
        oss_domain=(os.getenv("OSS_DOMAIN") or "").strip().rstrip("/"),
        oss_path_prefix=(os.getenv("OSS_PATH_PREFIX") or "cs/").strip() or "cs/",
        session_context_token_budget=max(
            512, _env_int("SESSION_CONTEXT_TOKEN_BUDGET", 3500)
        ),
    )
