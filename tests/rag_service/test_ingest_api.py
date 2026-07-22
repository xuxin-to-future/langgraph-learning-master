"""入库流水线单测（Task 3）。"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rag_service.api.app import create_app
from rag_service.config.settings import Settings, get_settings
from rag_service.services.chunking import split_text
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
    with TestClient(create_app()) as c:
        yield c


def test_split_by_heading() -> None:
    text = "# 政策\n\n前言\n\n## 退款政策\n\n购买后 7 天内可退款。\n\n## 其他\n\n说明"
    pieces = split_text(text, max_tokens=512, overlap_percent=0)
    assert len(pieces) >= 1
    assert any("退款" in p.text for p in pieces)


def test_upload_refund_md_ready(client: TestClient) -> None:
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
    body = resp.json()
    assert body["status"] == "ready"
    assert body["chunk_count"] >= 1
    assert body["doc_id"]

    # 文件已落盘
    detail = client.get(f"/v1/documents/{body['doc_id']}")
    assert detail.status_code == 200
    assert detail.json()["chunk_count"] >= 1


def test_reject_bad_extension(client: TestClient) -> None:
    resp = client.post(
        "/v1/kb/kb_default/documents",
        files={"file": ("malware.exe", b"abc", "application/octet-stream")},
    )
    assert resp.status_code == 400
    assert "不支持的文件类型" in resp.json()["detail"]


def test_upload_missing_kb(client: TestClient) -> None:
    resp = client.post(
        "/v1/kb/kb_not_exist/documents",
        files={"file": ("a.md", b"# hi", "text/markdown")},
    )
    assert resp.status_code == 400
    assert "知识库不存在" in resp.json()["detail"]
