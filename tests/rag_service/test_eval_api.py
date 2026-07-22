"""评测 API / 黄金集单测（Task 8）。"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rag_service.api.app import create_app
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
        "rag_service.services.embedding",
        "rag_service.services.retrieve",
    ):
        monkeypatch.setattr(f"{mod}.get_settings", _settings)
    init_db(db_path)
    return db_path


@pytest.fixture()
def client(rag_env: Path):
    with TestClient(create_app()) as c:
        yield c


def _upload_refund_policy(client: TestClient) -> None:
    content = (
        "# 支持与退款政策\n\n"
        "## 退款政策\n\n"
        "订阅类服务在购买后 7 天内可申请全额退款。\n"
    ).encode("utf-8")
    resp = client.post(
        "/v1/kb/kb_default/documents",
        files={"file": ("support-policy.md", content, "text/markdown")},
        data={"title": "退款政策"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ready"


def test_eval_run_refund_case_passes(client: TestClient) -> None:
    _upload_refund_policy(client)
    resp = client.post("/v1/eval/run", json={"kb_id": "kb_default"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] >= 1
    by_id = {c["id"]: c for c in body["cases"]}
    assert "refund-policy" in by_id
    assert by_id["refund-policy"]["passed"] is True
    assert body["all_passed"] is True
