"""工单服务单测（不经 HTTP）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from customer_service.services import tickets
from customer_service.tools.ticket_tools import create_ticket_tool, get_ticket_tool


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "tickets_test.db"


def test_create_then_get_ticket(db_path: Path) -> None:
    ticket_id = tickets.create_ticket(
        subject="无法登录",
        description="提示密码错误",
        session_id="user-42",
        problem_types=["系统 Bug", "个人反馈"],
        attachments=["https://example.com/a.png"],
        rating=2,
        reporter="admin",
        db_path=db_path,
    )
    assert ticket_id.startswith("TK-")

    row = tickets.get_ticket(ticket_id, db_path=db_path)
    assert row is not None
    assert row["ticket_id"] == ticket_id
    assert row["subject"] == "无法登录"
    assert row["description"] == "提示密码错误"
    assert row["status"] == "open"
    assert row["session_id"] == "user-42"
    assert row["created_at"]
    assert row["problem_types"] == ["系统 Bug", "个人反馈"]
    assert row["attachments"] == ["https://example.com/a.png"]
    assert row["rating"] == 2
    assert row["reporter"] == "admin"


def test_get_missing_ticket_returns_none(db_path: Path) -> None:
    tickets.init_db(db_path)
    assert tickets.get_ticket("TK-DOESNOTEXIST", db_path=db_path) is None


def test_create_ticket_from_description(db_path: Path) -> None:
    ticket_id = tickets.create_ticket(
        description="页面打不开",
        problem_types=["业务问题"],
        rating=3,
        db_path=db_path,
    )
    row = tickets.get_ticket(ticket_id, db_path=db_path)
    assert row is not None
    assert row["subject"] == "页面打不开"
    assert row["rating"] == 3


def test_create_ticket_rejects_bad_rating(db_path: Path) -> None:
    with pytest.raises(ValueError):
        tickets.create_ticket(
            description="x",
            rating=9,
            db_path=db_path,
        )


def test_ticket_tools_thin_wrapper(db_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "customer_service.services.tickets.get_settings",
        lambda: type(
            "S",
            (),
            {"tickets_db_path": db_path},
        )(),
    )
    ticket_id = create_ticket_tool("网络异常", "间歇性断线", "sess-1")
    found = get_ticket_tool(ticket_id)
    assert found is not None
    assert found["subject"] == "网络异常"
    assert get_ticket_tool("TK-MISSING") is None
