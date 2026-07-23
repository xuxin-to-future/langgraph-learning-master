"""转人工 / HITL 节点。"""

from __future__ import annotations

from langgraph.types import interrupt
from langchain_core.messages import AIMessage

from customer_service.graph.nodes._message_utils import last_user_text
from customer_service.models.state import SupportState
from customer_service.tools.escalate_tool import request_human_handoff


def escalate_node(state: SupportState) -> dict:
    """转人工：interrupt 暂停；resume 后写入最终 answer。

    首次命中 interrupt 时，图会暂停；API 层可根据中断信息返回 needs_human=true。
    本节点在 resume 之后返回最终回复，并将 needs_human 置为 False。
    """
    reason = last_user_text(state) or "用户请求人工协助"
    handoff = request_human_handoff(reason=reason, session_id="")

    # 暂停等待人工；resume 载荷建议为 str 或 {"message": "..."}
    resume_value = interrupt(handoff)

    if isinstance(resume_value, dict):
        human_msg = str(
            resume_value.get("message")
            or resume_value.get("reply")
            or resume_value
        )
    else:
        human_msg = str(resume_value)

    answer = f"人工客服已处理：{human_msg}"
    from customer_service.services.session_memory import (
        normalize_session_memory,
        touch_last_turns,
    )

    memory = touch_last_turns(
        normalize_session_memory(state.get("session_memory")),
        reason,
        answer,
    )
    return {
        "needs_human": False,
        "needs_ticket_form": False,
        "answer": answer,
        "error": None,
        "session_memory": memory,
        "messages": [AIMessage(content=answer)],
    }
