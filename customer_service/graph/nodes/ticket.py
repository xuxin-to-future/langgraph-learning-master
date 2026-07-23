"""工单节点：引导填写反馈表单（不再自动建单）。"""

from __future__ import annotations

from langchain_core.messages import AIMessage

from customer_service.graph.nodes._message_utils import last_user_text
from customer_service.models.state import SupportState
from customer_service.services.session_memory import (
    normalize_session_memory,
    touch_last_turns,
)


def ticket_node(state: SupportState) -> dict:
    query = last_user_text(state)
    answer = "检测到您想反馈问题或创建工单，请填写下方表单提交。"
    memory = touch_last_turns(
        normalize_session_memory(state.get("session_memory")),
        query,
        answer,
    )
    return {
        "ticket_id": None,
        "retrieved_docs": [],
        "needs_ticket_form": True,
        "needs_human": False,
        "answer": answer,
        "error": None,
        "session_memory": memory,
        "messages": [AIMessage(content=answer)],
    }
