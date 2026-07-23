"""Supervisor 意图解析单测。"""

from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage

from customer_service.graph.nodes.chitchat import chitchat_node
from customer_service.graph.nodes.faq import faq_node
from customer_service.graph.nodes.supervisor import (
    _parse_intent_label,
    classify_intent,
    load_supervisor_prompt,
    supervisor_node,
)
from customer_service.graph.nodes.ticket import ticket_node
from tests.customer_service.conftest import acceptance_intent


def test_supervisor_prompt_is_substantive() -> None:
    prompt = load_supervisor_prompt()
    assert "faq" in prompt
    assert "escalate" in prompt
    assert "ticket" in prompt
    assert "互斥" in prompt or "四选一" in prompt or "只输出" in prompt
    assert "傻逼系统" in prompt or "吐槽" in prompt
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
        ("烂系统", "ticket"),
        ("傻逼系统", "ticket"),
        ("这破软件天天卡死，我要反馈一下", "ticket"),
        ("我要投诉，找人工", "escalate"),
        ("你好呀", "chitchat"),
    ],
)
def test_acceptance_intent_stub(text: str, intent: str) -> None:
    """验收话术替身（仅测试用），验证用例覆盖与提示词设计一致。"""
    assert acceptance_intent(text) == intent


def test_classify_uses_llm_only(
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
        lambda _text, session_block="", turn_type="": "faq",
    )
    assert classify_intent("帮我建一个无法登录的工单") == "faq"


def test_classify_session_recall_short_circuits() -> None:
    assert (
        classify_intent("我刚才问的是什么", turn_type="session_recall") == "chitchat"
    )


def test_classify_without_key_falls_back_chitchat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _S:
        has_openai_key = False
        allow_offline_fallback = True
        openai_api_key = None
        openai_model = "dummy"
        openai_base_url = None

    monkeypatch.setattr(
        "customer_service.graph.nodes.supervisor.get_settings",
        lambda: _S(),
    )
    # 无 Key 时不得靠关键词猜意图
    assert classify_intent("帮我建一个无法登录的工单") == "chitchat"


def test_supervisor_node_resets_form_flag(
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
        lambda _text, session_block="", turn_type="": "escalate",
    )
    out = supervisor_node({"messages": [HumanMessage(content="随便说点什么")]})
    assert out["intent"] == "escalate"
    assert out["needs_ticket_form"] is False
    assert out["needs_human"] is False


def test_faq_node_retrieves_support_policy() -> None:
    out = faq_node({"messages": [HumanMessage(content="退款政策是什么？")]})
    assert out["answer"]
    assert out["retrieved_docs"]
    assert any("support-policy.md" in d for d in out["retrieved_docs"])
    assert out.get("needs_ticket_form") is False


def test_ticket_node_prompts_form() -> None:
    out = ticket_node(
        {"messages": [HumanMessage(content="帮我建一个无法登录的工单")]}
    )
    assert out.get("needs_ticket_form") is True
    assert out.get("ticket_id") is None
    assert "表单" in (out.get("answer") or "")


def test_chitchat_node_greeting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "customer_service.graph.nodes.chitchat._chitchat_with_llm",
        lambda *_a, **_k: None,
    )
    out = chitchat_node({"messages": [HumanMessage(content="你好")]})
    assert "智服助手" in out["answer"]
    assert out.get("needs_ticket_form") is False
