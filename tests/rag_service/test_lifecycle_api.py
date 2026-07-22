"""文档生命周期与 retrieve 过滤单测（Task 7）。"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rag_service.api.app import create_app
from rag_service.config.settings import Settings, get_settings
from rag_service.storage.db import connect, init_db


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
    ):
        monkeypatch.setattr(f"{mod}.get_settings", _settings)
    init_db(db_path)
    return db_path


@pytest.fixture()
def client(rag_env: Path):
    with TestClient(create_app()) as c:
        yield c


def _upload(client: TestClient, *, filename: str, content: str, title: str) -> dict:
    resp = client.post(
        "/v1/kb/kb_default/documents",
        files={"file": (filename, content.encode("utf-8"), "text/markdown")},
        data={"title": title},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ready"
    return body


def test_delete_document_removes_from_retrieve(client: TestClient, rag_env: Path) -> None:
    doc = _upload(
        client,
        filename="refund.md",
        content="# 退款\n\n订阅类服务 7 天内可全额退款。\n",
        title="退款政策",
    )
    doc_id = doc["doc_id"]

    hit = client.post(
        "/v1/retrieve",
        json={"kb_id": "kb_default", "query": "退款", "methods": ["keyword"], "top_k": 5},
    )
    assert hit.status_code == 200
    assert any(c["doc_id"] == doc_id for c in hit.json()["chunks"])

    deleted = client.delete(f"/v1/documents/{doc_id}")
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deleted"

    missing = client.get(f"/v1/documents/{doc_id}")
    assert missing.status_code == 404

    with connect(rag_env) as conn:
        n_chunks = conn.execute(
            "SELECT COUNT(*) AS n FROM chunks WHERE doc_id = ?", (doc_id,)
        ).fetchone()["n"]
        assert n_chunks == 0
        n_docs = conn.execute(
            "SELECT COUNT(*) AS n FROM documents WHERE doc_id = ?", (doc_id,)
        ).fetchone()["n"]
        assert n_docs == 0

    after = client.post(
        "/v1/retrieve",
        json={"kb_id": "kb_default", "query": "退款", "methods": ["keyword"], "top_k": 5},
    )
    assert after.status_code == 200
    assert all(c["doc_id"] != doc_id for c in after.json()["chunks"])


def test_retrieve_filters_doc_ids(client: TestClient) -> None:
    a = _upload(
        client,
        filename="refund-a.md",
        content="# A\n\n退款政策 A：7 天内退款。\n",
        title="政策A",
    )
    b = _upload(
        client,
        filename="refund-b.md",
        content="# B\n\n退款政策 B：15 天内退款。\n",
        title="政策B",
    )

    resp = client.post(
        "/v1/retrieve",
        json={
            "kb_id": "kb_default",
            "query": "退款政策",
            "methods": ["keyword"],
            "top_k": 10,
            "filters": {"doc_ids": [a["doc_id"]]},
        },
    )
    assert resp.status_code == 200, resp.text
    chunks = resp.json()["chunks"]
    assert chunks, "过滤后应仍能命中文档 A"
    assert all(c["doc_id"] == a["doc_id"] for c in chunks)
    assert all(c["doc_id"] != b["doc_id"] for c in chunks)


def test_reindex_document_ready(client: TestClient, rag_env: Path) -> None:
    doc = _upload(
        client,
        filename="ship.md",
        content="# 发货\n\n3 个工作日内发出。\n",
        title="发货",
    )
    doc_id = doc["doc_id"]
    with connect(rag_env) as conn:
        row = conn.execute(
            "SELECT file_path FROM documents WHERE doc_id = ?", (doc_id,)
        ).fetchone()
        path = Path(row["file_path"])
    path.write_text("# 发货\n\n次日达快递已开通。\n", encoding="utf-8")

    resp = client.post(f"/v1/documents/{doc_id}/reindex")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ready"
    assert body["chunk_count"] >= 1

    hit = client.post(
        "/v1/retrieve",
        json={
            "kb_id": "kb_default",
            "query": "次日达",
            "methods": ["keyword"],
            "top_k": 5,
            "filters": {"doc_ids": [doc_id]},
        },
    )
    assert hit.status_code == 200
    texts = " ".join(c["text"] for c in hit.json()["chunks"])
    assert "次日达" in texts


def test_admin_page_has_lifecycle_actions(client: TestClient) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert "操作" in resp.text
    js = client.get("/js/app.js")
    assert js.status_code == 200
    assert "data-action=\"delete\"" in js.text or "data-action=\"delete\"" in resp.text or "delete" in js.text
    assert "/reindex" in js.text
