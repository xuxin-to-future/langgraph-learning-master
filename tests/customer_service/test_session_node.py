"""session 节点与路由单测。"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

from customer_service.graph.edges import route_by_intent
from customer_service.graph.nodes.chitchat import chitchat_node
from customer_service.graph.nodes.session import session_node
from customer_service.services.session_analyze import SessionAnalyzeResult
from customer_service.services.session_memory import empty_session_memory


def test_route_session_recall_to_chitchat() -> None:
    assert (
        route_by_intent({"turn_type": "session_recall", "intent": "faq"}) == "chitchat"
    )


def test_session_node_writes_fields(monkeypatch) -> None:
    mem = empty_session_memory()
    mem["last_user_question"] = "商机周期是什么"

    def fake_analyze(text, *, prompt_block="", memory=None, has_history=False):
        return SessionAnalyzeResult(
            turn_type="followup",
            need_retrieve=True,
            standalone_query="商机周期 整理成计算公式",
            session_memory=mem,
        )

    monkeypatch.setattr(
        "customer_service.graph.nodes.session.analyze_turn",
        fake_analyze,
    )
    monkeypatch.setattr(
        "customer_service.graph.nodes.session.prepare_session_update",
        lambda _state: {},
    )

    out = session_node(
        {
            "messages": [
                HumanMessage(content="商机周期是什么"),
                AIMessage(content="有效期 90 天"),
                HumanMessage(content="整理成计算公式"),
            ],
            "session_memory": mem,
            "conversation_summary": "",
        }
    )
    assert out["turn_type"] == "followup"
    assert out["need_retrieve"] is True
    assert "商机" in out["standalone_query"]


def test_chitchat_recall_uses_last_question() -> None:
    mem = empty_session_memory()
    mem["last_user_question"] = "商机生命周期是什么"
    out = chitchat_node(
        {
            "messages": [HumanMessage(content="我刚才问的是什么")],
            "turn_type": "session_recall",
            "session_memory": mem,
            "conversation_summary": "",
        }
    )
    assert "商机生命周期" in out["answer"]
    assert out["retrieved_docs"] == []
