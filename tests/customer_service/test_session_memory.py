"""多轮工作记忆与启发式会话更新单测。"""

from __future__ import annotations

from customer_service.services.session_memory import (
    empty_session_memory,
    heuristic_session_update,
    normalize_session_memory,
    touch_last_turns,
)


def test_normalize_fills_defaults() -> None:
    m = normalize_session_memory(None)
    assert m["topic"] == ""
    assert m["slots"] == {}
    assert m["entities"] == []


def test_heuristic_followup_when_history() -> None:
    prev = empty_session_memory()
    prev["topic"] = "商机有效期"
    prev["last_user_question"] = "商机周期是什么"
    out = heuristic_session_update("整理成计算公式", prev, has_history=True)
    assert out["turn_type"] == "followup"
    assert out["need_retrieve"] is True
    assert "商机" in out["standalone_query"] or "周期" in out["standalone_query"]
    assert "整理成计算公式" in out["standalone_query"]


def test_heuristic_recall() -> None:
    prev = empty_session_memory()
    prev["last_user_question"] = "退款政策"
    out = heuristic_session_update("我刚才问的是什么", prev, has_history=True)
    assert out["turn_type"] == "session_recall"
    assert out["need_retrieve"] is False


def test_touch_last_turns() -> None:
    m = touch_last_turns(empty_session_memory(), "q1", "a1")
    assert m["last_user_question"] == "q1"
    assert m["last_assistant_answer"] == "a1"
