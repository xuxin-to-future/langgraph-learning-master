"""编译客服 StateGraph。"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from customer_service.graph.edges import route_by_intent
from customer_service.graph.nodes.chitchat import chitchat_node
from customer_service.graph.nodes.escalate import escalate_node
from customer_service.graph.nodes.faq import faq_node
from customer_service.graph.nodes.session import session_node
from customer_service.graph.nodes.supervisor import supervisor_node
from customer_service.graph.nodes.ticket import ticket_node
from customer_service.models.state import SupportState
from customer_service.services.memory import get_checkpointer

_graph_singleton: Any | None = None


def build_graph(*, checkpointer: Any = None) -> Any:
    """构建并 compile 客服图。

    Args:
        checkpointer: 可选；默认使用 `get_checkpointer()`。
    """
    workflow = StateGraph(SupportState)

    workflow.add_node("session", session_node)
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("faq", faq_node)
    workflow.add_node("ticket", ticket_node)
    workflow.add_node("chitchat", chitchat_node)
    workflow.add_node("escalate", escalate_node)

    workflow.add_edge(START, "session")
    workflow.add_edge("session", "supervisor")
    workflow.add_conditional_edges(
        "supervisor",
        route_by_intent,
        {
            "faq": "faq",
            "ticket": "ticket",
            "chitchat": "chitchat",
            "escalate": "escalate",
        },
    )
    workflow.add_edge("faq", END)
    workflow.add_edge("ticket", END)
    workflow.add_edge("chitchat", END)
    workflow.add_edge("escalate", END)

    cp = get_checkpointer() if checkpointer is None else checkpointer
    return workflow.compile(checkpointer=cp)


def get_compiled_graph(*, force_reload: bool = False) -> Any:
    """懒加载单例编译图（供 API 复用）。"""
    global _graph_singleton
    if _graph_singleton is None or force_reload:
        # 提示词文件有 lru_cache，热重载时一并清掉
        try:
            from customer_service.graph.nodes.supervisor import load_supervisor_prompt

            load_supervisor_prompt.cache_clear()
        except Exception:  # noqa: BLE001
            pass
        try:
            from customer_service.services.session_analyze import load_session_prompt

            load_session_prompt.cache_clear()
        except Exception:  # noqa: BLE001
            pass
        _graph_singleton = build_graph()
    return _graph_singleton


def reset_compiled_graph() -> None:
    """测试用：清空单例。"""
    global _graph_singleton
    _graph_singleton = None
