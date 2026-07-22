"""工单节点。"""

from __future__ import annotations

from customer_service.graph.nodes._message_utils import last_user_text
from customer_service.models.state import SupportState
from customer_service.tools.ticket_tools import create_ticket_tool


def _subject_from_text(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return "用户反馈"
    # 截断过长主题
    return t if len(t) <= 80 else t[:77] + "..."


def ticket_node(state: SupportState) -> dict:
    text = last_user_text(state)
    subject = _subject_from_text(text)
    # session_id 若已由 API 写入消息 metadata，一期可留空；后续 builder/API 可扩展
    session_id = ""
    try:
        ticket_id = create_ticket_tool(
            subject=subject,
            description=text,
            session_id=session_id,
        )
        return {
            "ticket_id": ticket_id,
            "answer": f"已为您创建工单，编号：{ticket_id}。我们会尽快跟进处理。",
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ticket_id": None,
            "answer": "工单创建失败，请稍后重试或转人工。",
            "error": str(exc),
        }
