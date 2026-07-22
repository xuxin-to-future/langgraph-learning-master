"""知识库搜索工具（供图节点调用的薄封装）。"""

from __future__ import annotations

from customer_service.services import rag


def search_knowledge(query: str, *, top_k: int = 4) -> list[str]:
    """按关键词检索知识库，返回带来源的文本片段。"""
    return rag.retrieve(query, top_k=top_k)


def answer_from_knowledge(query: str, *, top_k: int = 4) -> str:
    """检索并生成 FAQ 回答（优先大模型）。"""
    answer, _docs = rag.answer_faq(query, top_k=top_k, use_llm=True)
    return answer
