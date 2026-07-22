"""Supervisor 意图解析与离线降级单测。"""

from __future__ import annotations

from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from customer_service.graph.nodes.chitchat import chitchat_node
from customer_service.graph.nodes.faq import faq_node
from customer_service.graph.nodes.supervisor import (
    _parse_intent_label,
    classify_intent,
    classify_intent_by_rules,
    load_supervisor_prompt,
    supervisor_node,
)
from customer_service.graph.nodes.ticket import ticket_node
from customer_service.services import tickets as ticket_service


def test_supervisor_prompt_is_substantive() -> None:
    prompt = load_supervisor_prompt()
    assert "faq" in prompt
    assert "escalate" in prompt
    assert "只输出" in prompt or "输出格式" in prompt
    assert len(prompt) > 200


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("faq", "faq"),
        ("FAQ", "faq"),
        ('{"intent":"ticket"}', "ticket"),
        ("意图：escalate\n", "escalate"),
        ("chitchat", "chitchat"),
    ],
)
def test_parse_intent_label(raw: str, expected: str) -> None:
    assert _parse_intent_label(raw) == expected


@pytest.mark.parametrize(
    ("text", "intent"),
    [
        ("退款政策是什么？", "faq"),
        ("帮我建一个无法登录的工单", "ticket"),
        ("我要投诉，找人工", "escalate"),
        ("你好呀", "chitchat"),
    ],
)
def test_rule_fallback_acceptance_phrases(text: str, intent: str) -> None:
    """规则仅作离线降级，仍覆盖三验收话术。"""
    assert classify_intent_by_rules(text) == intent


def test_classify_prefers_llm_when_key_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _S:
        has_openai_key = True
        allow_offline_fallback = True
        openai_api_key = "sk-test"
        openai_model = "dummy"
        openai_base_url = None

    monkeypatch.setattr(
        "customer_service.graph.nodes.supervisor.get_settings",
        lambda: _S(),
    )
    monkeypatch.setattr(
        "customer_service.graph.nodes.supervisor._classify_intent_by_llm",
        lambda _text: "faq",
    )
    # 即使文案像工单，也应以模型结果为准
    assert classify_intent("帮我建一个无法登录的工单") == "faq"


def test_supervisor_node_uses_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _S:
        has_openai_key = True
        allow_offline_fallback = True
        openai_api_key = "sk-test"
        openai_model = "dummy"
        openai_base_url = None

    monkeypatch.setattr(
        "customer_service.graph.nodes.supervisor.get_settings",
        lambda: _S(),
    )
    monkeypatch.setattr(
        "customer_service.graph.nodes.supervisor._classify_intent_by_llm",
        lambda _text: "escalate",
    )
    out = supervisor_node({"messages": [HumanMessage(content="随便说点什么")]})
    assert out["intent"] == "escalate"


def test_supervisor_node_offline_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _S:
        has_openai_key = False
        allow_offline_fallback = True

    monkeypatch.setattr(
        "customer_service.graph.nodes.supervisor.get_settings",
        lambda: _S(),
    )
    out = supervisor_node({"messages": [HumanMessage(content="退款政策是什么？")]})
    assert out["intent"] == "faq"


def test_faq_node_retrieves_support_policy() -> None:
    out = faq_node({"messages": [HumanMessage(content="退款政策是什么？")]})
    assert out["answer"]
    assert out["retrieved_docs"]
    assert any("support-policy.md" in d for d in out["retrieved_docs"])


def test_ticket_node_creates_ticket(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "t.db"
    monkeypatch.setattr(
        "customer_service.services.tickets.get_settings",
        lambda: type("S", (), {"tickets_db_path": db})(),
    )
    out = ticket_node(
        {"messages": [HumanMessage(content="帮我建一个无法登录的工单")]}
    )
    assert out["ticket_id"]
    assert out["ticket_id"].startswith("TK-")
    assert ticket_service.get_ticket(out["ticket_id"], db_path=db) is not None


def test_chitchat_node_greeting() -> None:
    out = chitchat_node({"messages": [HumanMessage(content="你好")]})
    assert "智服助手" in out["answer"]
