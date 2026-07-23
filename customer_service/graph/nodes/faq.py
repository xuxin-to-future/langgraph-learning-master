"""FAQ / RAG 节点（会话门控检索 + 多轮生成）。"""

from __future__ import annotations

from langchain_core.messages import AIMessage

from customer_service.graph.nodes._message_utils import (
    last_user_text,
    session_context_from_state,
)
from customer_service.models.state import SupportState
from customer_service.services import rag
from customer_service.services.session_memory import (
    normalize_session_memory,
    touch_last_turns,
)


def faq_node(state: SupportState) -> dict:
    query = last_user_text(state)
    ctx = session_context_from_state(state)
    need_retrieve = state.get("need_retrieve")
    if need_retrieve is None:
        need_retrieve = True
    standalone = (state.get("standalone_query") or "").strip() or query
    try:
        answer, docs = rag.answer_faq(
            query,
            use_llm=True,
            conversation_block=ctx.prompt_block,
            search_query=standalone if need_retrieve else None,
            skip_retrieve=not bool(need_retrieve),
        )
        memory = touch_last_turns(
            normalize_session_memory(state.get("session_memory")),
            query,
            answer,
        )
        return {
            "retrieved_docs": docs,
            "answer": answer,
            "error": None,
            "needs_ticket_form": False,
            "needs_human": False,
            "session_memory": memory,
            "messages": [AIMessage(content=answer)],
        }
    except Exception as exc:  # noqa: BLE001 — 节点内可恢复错误
        answer = "知识库暂时不可用，请稍后再试或转人工。"
        memory = touch_last_turns(
            normalize_session_memory(state.get("session_memory")),
            query,
            answer,
        )
        return {
            "retrieved_docs": [],
            "answer": answer,
            "error": str(exc),
            "needs_ticket_form": False,
            "needs_human": False,
            "session_memory": memory,
            "messages": [AIMessage(content=answer)],
        }
