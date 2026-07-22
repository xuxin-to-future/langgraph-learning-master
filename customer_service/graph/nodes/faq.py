"""FAQ / RAG 节点。"""

from __future__ import annotations

from customer_service.graph.nodes._message_utils import last_user_text
from customer_service.models.state import SupportState
from customer_service.services import rag


def faq_node(state: SupportState) -> dict:
    query = last_user_text(state)
    try:
        # 检索 +（有 Key 时）大模型生成；失败则离线模板
        # top_k / provider 由 Settings（RAG_*）决定，节点无需改图
        answer, docs = rag.answer_faq(query, use_llm=True)
        return {
            "retrieved_docs": docs,
            "answer": answer,
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001 — 节点内可恢复错误
        return {
            "retrieved_docs": [],
            "answer": "知识库暂时不可用，请稍后再试或转人工。",
            "error": str(exc),
        }
