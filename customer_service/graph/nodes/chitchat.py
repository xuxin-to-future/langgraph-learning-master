"""寒暄节点。"""

from __future__ import annotations

from customer_service.graph.nodes._message_utils import last_user_text
from customer_service.models.state import SupportState


def chitchat_node(state: SupportState) -> dict:
    text = last_user_text(state)
    lower = text.lower()
    if any(k in text for k in ("你好", "您好", "嗨", "hello", "hi")) or "hello" in lower:
        answer = "您好！我是智服助手，可以帮您查询政策、创建工单，或在需要时转接人工。"
    elif any(k in text for k in ("谢谢", "感谢", "拜拜", "再见")):
        answer = "不客气，有需要随时找我。"
    else:
        answer = (
            "我更擅长解答产品/政策问题、帮您创建工单，或转接人工客服。"
            "您可以直接描述问题，例如「退款政策是什么？」"
        )
    return {"answer": answer, "error": None}
