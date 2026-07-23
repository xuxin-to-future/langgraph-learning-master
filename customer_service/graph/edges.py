"""条件边与路由辅助。"""

from __future__ import annotations

from customer_service.models.state import Intent, SupportState


def route_by_intent(state: SupportState) -> Intent:
    """根据 turn_type / intent 返回下一节点名。"""
    if state.get("turn_type") == "session_recall":
        return "chitchat"
    intent = state.get("intent")
    if intent is None:
        raise ValueError("state.intent is required before routing")
    return intent
