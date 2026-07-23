"""escalate interrupt → resume 端到端测试。"""

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


def test_escalate_then_resume(client: TestClient) -> None:
    session_id = "sess-hitl-1"

    paused = client.post(
        "/v1/chat",
        json={"sessionId": session_id, "message": "我要投诉，找人工"},
    )
    assert paused.status_code == 200
    data = paused.json()
    assert data["intent"] == "escalate"
    assert data["needs_human"] is True
    assert data["answer"]

    resumed = client.post(
        f"/v1/admin/escalate/{session_id}/resume",
        json={"message": "已记录投诉并回电用户", "approve": True},
    )
    assert resumed.status_code == 200
    body = resumed.json()
    assert body["sessionId"] == session_id
    assert body["needs_human"] is False
    assert "人工客服已处理" in body["answer"]
    assert "已记录投诉" in body["answer"]
