"""RAG 知识库 API 单测（Task 1–2）。"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rag_service.api.app import create_app
from rag_service.config.settings import Settings, get_settings
from rag_service.services import kb as kb_service
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
    monkeypatch.setattr("rag_service.config.settings.get_settings", _settings)
    monkeypatch.setattr("rag_service.storage.db.get_settings", _settings)
    monkeypatch.setattr("rag_service.services.kb.get_settings", _settings)
    init_db(db_path)
    return db_path


@pytest.fixture()
def client(rag_env: Path):
    with TestClient(create_app()) as c:
        yield c


def test_health(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_create_and_list_kb(client: TestClient) -> None:
    created = client.post(
        "/v1/kb",
        json={"name": "客服政策", "description": "demo"},
    )
    assert created.status_code == 200
    body = created.json()
    assert body["name"] == "客服政策"
    assert body["kb_id"]

    listed = client.get("/v1/kb")
    assert listed.status_code == 200
    names = {item["name"] for item in listed.json()}
    # lifespan / list 会确保 default 存在
    assert "客服政策" in names
    assert "default" in names


def test_get_kb_detail(client: TestClient) -> None:
    created = client.post("/v1/kb", json={"name": "产品说明"})
    kb_id = created.json()["kb_id"]
    detail = client.get(f"/v1/kb/{kb_id}")
    assert detail.status_code == 200
    assert detail.json()["kb_id"] == kb_id

    missing = client.get("/v1/kb/kb_not_exist")
    assert missing.status_code == 404


def test_ensure_default_kb(rag_env: Path) -> None:
    row = kb_service.ensure_default_kb(db_path=rag_env)
    assert row["kb_id"] == "kb_default"
    again = kb_service.ensure_default_kb(db_path=rag_env)
    assert again["kb_id"] == row["kb_id"]
