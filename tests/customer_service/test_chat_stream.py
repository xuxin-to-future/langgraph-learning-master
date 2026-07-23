"""流式对话 SSE 单测。"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver

from customer_service.api.app import create_app
from customer_service.graph.builder import build_graph


@pytest.fixture()
def force_rules(mock_intent_llm: None) -> None:
    return None


@pytest.fixture()
def client(
    force_rules: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> TestClient:
    db = tmp_path / "tickets.db"

    class _TicketSettings:
        tickets_db_path = db

    monkeypatch.setattr(
        "customer_service.services.tickets.get_settings",
        lambda: _TicketSettings(),
    )
    app = create_app(graph=build_graph(checkpointer=MemorySaver()))
    return TestClient(app)


def test_chat_stream_sse_faq(client: TestClient) -> None:
    with client.stream(
        "POST",
        "/v1/chat/stream",
        json={"sessionId": "stream-1", "message": "退款政策是什么？"},
    ) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")
        raw = "".join(resp.iter_text())

    assert "data:" in raw
    assert '"type": "start"' in raw or '"type":"start"' in raw
    assert '"type": "done"' in raw or '"type":"done"' in raw
    assert "退款" in raw or "support-policy" in raw or "faq" in raw
