"""召回 API 单测（Task 4）。"""

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
            openai_api_key=None,  # 单测强制仅关键词，避免外网
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


def test_retrieve_refund_hits_source(client: TestClient) -> None:
    _upload_refund_policy(client)

    resp = client.post(
        "/v1/retrieve",
        json={
            "kb_id": "kb_default",
            "query": "退款政策是什么？",
            "top_k": 5,
            "methods": ["keyword"],
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["query"] == "退款政策是什么？"
    assert body["chunks"], "应至少命中一条"
    top = body["chunks"][0]
    assert top["chunk_id"]
    assert top["doc_id"]
    assert top["kb_id"] == "kb_default"
    assert top["source"] == "support-policy.md"
    assert "退款" in top["text"] or "退款" in top["source"]
    assert isinstance(top["score"], (int, float))


def test_retrieve_keyword_only_works(client: TestClient) -> None:
    _upload_refund_policy(client)
    resp = client.post(
        "/v1/retrieve",
        json={
            "kb_id": "kb_default",
            "query": "7 天内退款",
            "methods": ["keyword"],
            "top_k": 3,
        },
    )
    assert resp.status_code == 200
    assert len(resp.json()["chunks"]) >= 1


def test_retrieve_vector_only_without_embeddings_empty(client: TestClient) -> None:
    _upload_refund_policy(client)
    resp = client.post(
        "/v1/retrieve",
        json={
            "kb_id": "kb_default",
            "query": "退款政策是什么？",
            "methods": ["vector"],
            "top_k": 5,
        },
    )
    assert resp.status_code == 200
    # 无 embedding Key / 无向量时不报错，可为清空
    assert resp.json()["chunks"] == []


def _upload_multi_section_policy(client: TestClient) -> None:
    """多章节长文档，便于初召 > top_k（每节故意加长以跨过 token 预算）。"""
    filler = "说明文字。" * 80
    content = (
        "# 支持文档\n\n"
        f"## 退款政策\n\n订阅类服务在购买后 7 天内可申请全额退款。{filler}\n\n"
        f"## 发货说明\n\n实物商品一般 3 个工作日内发出。{filler}\n\n"
        f"## 发票开具\n\n企业用户可申请增值税专用发票。{filler}\n\n"
        f"## 账号安全\n\n请勿向他人泄露验证码与密码。{filler}\n\n"
        f"## 联系客服\n\n工作日 9:00-18:00 在线支持。{filler}\n"
    ).encode("utf-8")
    resp = client.post(
        "/v1/kb/kb_default/documents",
        files={"file": ("multi-policy.md", content, "text/markdown")},
        data={"title": "多章节政策"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ready"
    assert resp.json()["chunk_count"] >= 2


def test_retrieve_rerank_true_returns_at_most_top_k(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """rerank=true 时返回条数 ≤ top_k；无模型降级也不超限。"""
    _upload_multi_section_policy(client)

    resp = client.post(
        "/v1/retrieve",
        json={
            "kb_id": "kb_default",
            "query": "退款政策",
            "methods": ["keyword"],
            "top_k": 2,
            "recall_top_n": 10,
            "rerank": True,
        },
    )
    assert resp.status_code == 200, resp.text
    chunks = resp.json()["chunks"]
    assert len(chunks) <= 2
    assert len(chunks) >= 1


def test_retrieve_rerank_applies_when_model_available(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """有重排实现时，按 rerank 分排序并写入 score_detail.rerank。"""
    from rag_service.services.retrieve import Hit

    _upload_multi_section_policy(client)

    def _fake_rerank(query: str, hits: list[Hit]) -> list[Hit]:
        out: list[Hit] = []
        for i, hit in enumerate(reversed(hits)):
            score = 1.0 - i * 0.01
            detail = dict(hit.score_detail)
            detail["rerank"] = score
            out.append(
                Hit(
                    chunk_id=hit.chunk_id,
                    doc_id=hit.doc_id,
                    kb_id=hit.kb_id,
                    source=hit.source,
                    text=hit.text,
                    score=score,
                    score_detail=detail,
                )
            )
        return out

    monkeypatch.setattr("rag_service.services.retrieve.try_rerank", _fake_rerank)

    resp = client.post(
        "/v1/retrieve",
        json={
            "kb_id": "kb_default",
            "query": "退款",
            "methods": ["keyword"],
            "top_k": 2,
            "recall_top_n": 10,
            "rerank": True,
        },
    )
    assert resp.status_code == 200, resp.text
    chunks = resp.json()["chunks"]
    assert 1 <= len(chunks) <= 2
    for c in chunks:
        assert c["score_detail"]["rerank"] is not None
    if len(chunks) >= 2:
        assert chunks[0]["score"] >= chunks[1]["score"]
