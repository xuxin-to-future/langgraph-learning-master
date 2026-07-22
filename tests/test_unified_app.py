"""统一应用入口冒烟单测。"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from rag_service.config.settings import Settings, get_settings
from rag_service.storage.db import init_db


@pytest.fixture()
def rag_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "rag"
    db_path = data_dir / "rag.db"
    files_dir = data_dir / "files"

    def _settings() -> Settings:
        return Settings(
            data_dir=data_dir,
            db_path=db_path,
            files_dir=files_dir,
            max_upload_bytes=2 * 1024 * 1024,
            allowed_extensions=frozenset({".md", ".txt"}),
            default_kb_name="default",
            default_kb_id="kb_default",
            openai_api_key=None,
            openai_base_url=None,
            embedding_api_key=None,
            embedding_base_url=None,
            embedding_model="BAAI/bge-m3",
            rerank_api_key=None,
            rerank_base_url=None,
            rerank_model="BAAI/bge-reranker-v2-m3",
            vector_similarity_weight=0.7,
            chunk_token_num=512,
            chunk_overlap_percent=10,
            chunk_max_chars=8000,
        )

    get_settings.cache_clear()
    for mod in (
        "rag_service.config.settings",
        "rag_service.storage.db",
        "rag_service.services.kb",
        "rag_service.services.ingest",
    ):
        monkeypatch.setattr(f"{mod}.get_settings", _settings)
    init_db(db_path)
    return db_path


@pytest.fixture()
def client(rag_env: Path):
    class _FakeGraph:
        pass

    with TestClient(create_app(graph=_FakeGraph())) as c:
        yield c


def test_unified_health(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body.get("app") == "unified"


def test_unified_kb_page(client: TestClient) -> None:
    resp = client.get("/kb/")
    assert resp.status_code == 200
    assert "RAG" in resp.text or "知识库" in resp.text


def test_unified_kb_list_api(client: TestClient) -> None:
    resp = client.get("/v1/kb")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
