"""API 冒烟与 FAQ 对话测试。"""

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


def test_health(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_chat_faq_200(client: TestClient) -> None:
    resp = client.post(
        "/v1/chat",
        json={"sessionId": "user-42", "message": "退款政策是什么？"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["sessionId"] == "user-42"
    assert data["intent"] == "faq"
    assert data["answer"]
    assert data["needs_human"] is False
    assert any("support-policy" in c for c in data.get("citations", []))


def test_chat_missing_session_id_400(client: TestClient) -> None:
    resp = client.post("/v1/chat", json={"message": "你好"})
    assert resp.status_code == 400


def test_chat_new_session_command(client: TestClient) -> None:
    resp = client.post(
        "/v1/chat",
        json={"sessionId": "old-session", "message": "/new"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["sessionReset"] is True
    assert data["sessionId"] != "old-session"
    assert "新会话" in data["answer"]


def test_get_ticket_after_create(client: TestClient) -> None:
    create = client.post(
        "/v1/tickets",
        json={
            "problemTypes": ["系统 Bug"],
            "description": "无法登录，提示密码错误",
            "rating": 2,
            "attachments": [],
            "sessionId": "user-42",
        },
    )
    assert create.status_code == 200
    ticket_id = create.json()["ticket_id"]
    assert ticket_id
    assert create.json()["reporter"] == "admin"
    assert create.json()["problemTypes"] == ["系统 Bug"]
    assert create.json()["rating"] == 2
    assert create.json()["ratingLabel"] == "较差"

    got = client.get(f"/v1/tickets/{ticket_id}")
    assert got.status_code == 200
    assert got.json()["ticket_id"] == ticket_id

    missing = client.get("/v1/tickets/TK-MISSING")
    assert missing.status_code == 404


def test_chat_ticket_opens_form(client: TestClient) -> None:
    resp = client.post(
        "/v1/chat",
        json={
            "sessionId": "user-42",
            "message": "帮我建一个无法登录的工单",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["intent"] == "ticket"
    assert data["needsTicketForm"] is True
    assert data.get("ticket_id") in (None, "")


def test_upload_attachment_mocked(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "customer_service.api.routes_admin.upload_ticket_image",
        lambda **kwargs: "https://example.com/cs/tickets/demo.png",
    )
    resp = client.post(
        "/v1/tickets/attachments",
        files={"file": ("shot.png", b"fake-image-bytes", "image/png")},
    )
    assert resp.status_code == 200
    assert resp.json()["url"].endswith("demo.png")


def test_create_ticket_validation(client: TestClient) -> None:
    resp = client.post(
        "/v1/tickets",
        json={
            "problemTypes": [],
            "description": "x",
            "rating": 3,
        },
    )
    assert resp.status_code == 400
