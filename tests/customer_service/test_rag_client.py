"""HTTP RAG 客户端单测。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from customer_service.config.settings import Settings, get_settings
from customer_service.services import rag_client


@pytest.fixture()
def http_settings(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    data_dir = tmp_path / "data"
    s = Settings(
        knowledge_dir=tmp_path / "knowledge",
        data_dir=data_dir,
        tickets_db_path=data_dir / "tickets.db",
        chroma_dir=data_dir / "chroma",
        checkpointer_backend="memory",
        checkpointer_sqlite_path=data_dir / "checkpoints.sqlite",
        openai_api_key=None,
        openai_model="dummy",
        openai_base_url=None,
        allow_offline_fallback=True,
        rag_provider="http",
        # 非本机回环，走真实 HTTP 客户端路径（避免进程内直调）
        rag_base_url="http://rag.example.local:8100",
        rag_kb_id="kb_default",
        rag_top_k=3,
        rag_rerank=False,
        rag_api_key=None,
    )
    get_settings.cache_clear()
    monkeypatch.setattr("customer_service.services.rag_client.get_settings", lambda: s)
    monkeypatch.setattr("customer_service.config.settings.get_settings", lambda: s)
    return s


def test_rag_client_retrieve_maps_chunks(http_settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "query": "离职交接给谁？",
        "chunks": [
            {
                "source": "离职交接操作流程.md",
                "text": "客户分配人指离职销售的直属上级",
            }
        ],
    }
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.return_value = mock_resp
    monkeypatch.setattr(rag_client.httpx, "Client", lambda **kwargs: mock_client)

    docs = rag_client.retrieve("离职交接给谁？")
    assert len(docs) == 1
    assert docs[0].startswith("[离职交接操作流程.md]")
    assert "直属上级" in docs[0]
    body = mock_client.post.call_args.kwargs["json"]
    assert body["kb_id"] == "kb_default"
    assert body["top_k"] == 3
    assert body["rerank"] is False


def test_rag_client_loopback_uses_inprocess(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "data"
    s = Settings(
        knowledge_dir=tmp_path / "knowledge",
        data_dir=data_dir,
        tickets_db_path=data_dir / "tickets.db",
        chroma_dir=data_dir / "chroma",
        checkpointer_backend="memory",
        checkpointer_sqlite_path=data_dir / "checkpoints.sqlite",
        openai_api_key=None,
        openai_model="dummy",
        openai_base_url=None,
        allow_offline_fallback=True,
        rag_provider="http",
        rag_base_url="http://127.0.0.1:8000",
        rag_kb_id="kb_default",
        rag_top_k=3,
        rag_rerank=False,
        rag_api_key=None,
    )
    monkeypatch.setattr("customer_service.services.rag_client.get_settings", lambda: s)
    monkeypatch.setattr(
        "customer_service.services.rag_client._retrieve_inprocess",
        lambda query, top_k, kb_id, rerank: [f"[inprocess]\n{query}:{kb_id}:{top_k}:{rerank}"],
    )
    docs = rag_client.retrieve("hello")
    assert docs == ["[inprocess]\nhello:kb_default:3:False"]


def test_retrieve_docs_dispatches_http(http_settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    from customer_service.services import rag

    monkeypatch.setattr(
        "customer_service.services.rag.get_settings",
        lambda: http_settings,
    )
    monkeypatch.setattr(
        "customer_service.services.rag_client.retrieve",
        lambda query, top_k=None: [f"[http]\n{query}:{top_k}"],
    )
    docs = rag.retrieve_docs("退款政策")
    assert docs == ["[http]\n退款政策:3"]
