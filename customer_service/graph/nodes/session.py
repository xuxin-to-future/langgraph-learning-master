"""会话节点：压缩摘要 + 工作记忆 + turn 分析（在 supervisor 之前）。"""

from __future__ import annotations

from customer_service.graph.nodes._message_utils import (
    last_user_text,
    session_context_from_state,
)
from customer_service.models.state import SupportState
from customer_service.services.session import prepare_session_update
from customer_service.services.session_analyze import analyze_turn
from customer_service.services.session_memory import normalize_session_memory


def session_node(state: SupportState) -> dict:
    updates = prepare_session_update(dict(state))
    merged: dict = {**dict(state), **updates}

    text = last_user_text(merged)  # type: ignore[arg-type]
    ctx = session_context_from_state(merged)  # type: ignore[arg-type]
    memory = normalize_session_memory(merged.get("session_memory"))
    has_history = bool(
        memory.get("last_user_question")
        or memory.get("last_assistant_answer")
        or "助手：" in (ctx.prompt_block or "")
        or "会话摘要" in (ctx.prompt_block or "")
    )

    result = analyze_turn(
        text,
        prompt_block=ctx.prompt_block,
        memory=memory,
        has_history=has_history,
    )

    out: dict = {
        "turn_type": result.turn_type,
        "need_retrieve": result.need_retrieve,
        "standalone_query": result.standalone_query,
        "session_memory": result.session_memory,
    }
    out.update(updates)
    return out
