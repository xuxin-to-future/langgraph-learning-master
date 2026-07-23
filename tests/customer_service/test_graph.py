"""图级集成测试（不经 HTTP）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from customer_service.graph.builder import build_graph


@pytest.fixture()
def force_rules(mock_intent_llm: None) -> None:
    """兼容旧夹具名：改为 mock LLM 意图，不再走生产关键词。"""
    return None


@pytest.fixture()
def ticket_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db = tmp_path / "tickets.db"

    class _S:
        tickets_db_path = db

    monkeypatch.setattr(
        "customer_service.services.tickets.get_settings",
        lambda: _S(),
    )
    return db


def _invoke(graph: Any, text: str, thread_id: str) -> dict:
    return graph.invoke(
        {"messages": [HumanMessage(content=text)]},
        {"configurable": {"thread_id": thread_id}},
    )


def test_graph_faq_acceptance(force_rules: None) -> None:
    graph = build_graph(checkpointer=MemorySaver())
    result = _invoke(graph, "退款政策是什么？", "t-faq")
    assert result.get("intent") == "faq"
    assert result.get("answer")
    assert result.get("retrieved_docs")
    assert any("support-policy.md" in d for d in result["retrieved_docs"])
    assert "__interrupt__" not in result


def test_graph_ticket_acceptance(force_rules: None, ticket_db: Path) -> None:
    graph = build_graph(checkpointer=MemorySaver())
    result = _invoke(graph, "帮我建一个无法登录的工单", "t-ticket")
    assert result.get("intent") == "ticket"
    assert result.get("needs_ticket_form") is True
    assert not result.get("ticket_id")
    assert "表单" in (result.get("answer") or "")


def test_graph_escalate_interrupt_and_resume(force_rules: None) -> None:
    graph = build_graph(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "t-esc"}}

    first = graph.invoke(
        {"messages": [HumanMessage(content="我要投诉，找人工")]},
        cfg,
    )
    assert first.get("intent") == "escalate"
    assert "__interrupt__" in first
    interrupts = first["__interrupt__"]
    assert interrupts
    payload = interrupts[0].value
    assert payload.get("needs_human") is True

    second = graph.invoke(Command(resume="已安抚用户并记录投诉"), cfg)
    assert "__interrupt__" not in second
    assert second.get("needs_human") is False
    assert "人工客服已处理" in (second.get("answer") or "")
    assert "已安抚用户" in second["answer"]


def test_graph_followup_sets_standalone_query(force_rules: None) -> None:
    graph = build_graph(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "t-follow"}}
    first = graph.invoke(
        {"messages": [HumanMessage(content="退款政策是什么？")]},
        cfg,
    )
    assert first.get("intent") == "faq"
    # 模拟叶子已写入 last_user_question（faq_node 会写）
    second = graph.invoke(
        {"messages": [HumanMessage(content="整理成计算公式")]},
        cfg,
    )
    assert second.get("turn_type") == "followup"
    assert second.get("need_retrieve") is True
    sq = second.get("standalone_query") or ""
    assert "退款" in sq or "政策" in sq


def test_graph_session_recall(force_rules: None) -> None:
    graph = build_graph(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "t-recall"}}
    graph.invoke(
        {"messages": [HumanMessage(content="退款政策是什么？")]},
        cfg,
    )
    second = graph.invoke(
        {"messages": [HumanMessage(content="我刚才问的是什么")]},
        cfg,
    )
    assert second.get("turn_type") == "session_recall"
    assert second.get("need_retrieve") is False
    assert second.get("intent") == "chitchat"
    assert "退款政策" in (second.get("answer") or "")
    assert not second.get("retrieved_docs")
