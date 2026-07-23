"""会话管理单测：新会话命令、token 窗口、压缩触发。"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

from customer_service.services.session import (
    build_session_context,
    compress_session,
    count_tokens,
    is_new_session_command,
    needs_compression,
)


def test_new_session_commands() -> None:
    assert is_new_session_command("/new")
    assert is_new_session_command("新会话")
    assert is_new_session_command("新建会话")
    assert is_new_session_command("重新开始")
    assert not is_new_session_command("商机周期是什么？")
    assert not is_new_session_command("我想新建一个工单")


def test_build_session_context_keeps_recent_under_budget() -> None:
    messages = []
    for i in range(20):
        messages.append(HumanMessage(content=f"用户问题{i}：" + ("详情" * 40)))
        messages.append(AIMessage(content=f"助手回答{i}：" + ("说明" * 40)))
    ctx = build_session_context(messages, summary="", token_budget=800)
    assert ctx.recent_turns
    assert ctx.token_count <= 800 + 50
    assert any("用户问题19" in t or "助手回答19" in t for _, t in ctx.recent_turns)


def test_needs_compression_by_token_budget() -> None:
    messages = [
        HumanMessage(content="A" * 2000),
        AIMessage(content="B" * 2000),
    ]
    assert needs_compression(messages, summary="", token_budget=200)
    assert not needs_compression(
        [HumanMessage(content="短")],
        summary="",
        token_budget=3500,
    )


def test_compress_session_fallback_without_llm(monkeypatch) -> None:
    monkeypatch.setattr(
        "customer_service.services.session._summarize_with_llm",
        lambda _src: None,
    )
    messages = []
    for i in range(12):
        messages.append(HumanMessage(content=f"问{i} " + ("内容" * 80)))
        messages.append(AIMessage(content=f"答{i} " + ("回复" * 80)))
    summary = compress_session(messages, summary="", token_budget=400)
    assert isinstance(summary, str)
    assert count_tokens(summary) >= 1
