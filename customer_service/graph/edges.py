"""条件边与路由辅助（占位）。"""

from __future__ import annotations

from customer_service.models.state import Intent, SupportState


def route_by_intent(state: SupportState) -> Intent:
    """根据 state.intent 返回下一节点名。"""
    intent = state.get("intent")
    if intent is None:
        raise ValueError("state.intent is required before routing")
    return intent
