"""FAQ / RAG 检索与回答单测。"""

from __future__ import annotations

import pytest

from customer_service.config.settings import get_settings
from customer_service.services import rag
from customer_service.tools.kb_search import answer_from_knowledge, search_knowledge


def test_refund_policy_hits_support_policy() -> None:
    docs = rag.retrieve("退款政策是什么？", top_k=4)
    assert docs, "应检索到至少一个片段"
    joined = "\n".join(docs)
    assert "support-policy.md" in joined
    assert "退款" in joined


def test_answer_with_context_offline_template() -> None:
    docs = rag.retrieve("退款政策", top_k=2)
    answer = rag.answer_with_context("退款政策", docs)
    assert "退款政策" in answer
    assert "离线降级" in answer
    assert "support-policy.md" in answer


def test_answer_with_context_no_hit() -> None:
    answer = rag.answer_with_context("完全无关的火星移民政策xyz", [])
    assert "未找到" in answer


def test_kb_search_tool_wrapper(monkeypatch: pytest.MonkeyPatch) -> None:
    docs = search_knowledge("退款政策")
    assert any("support-policy.md" in d for d in docs)
    # 单测强制离线，避免依赖外网 LLM
    monkeypatch.setattr(
        "customer_service.services.rag.answer_faq",
        lambda query, top_k=4, use_llm=True, knowledge_dir=None: (
            rag.answer_with_context(query, rag.retrieve(query, top_k=top_k)),
            rag.retrieve(query, top_k=top_k),
        ),
    )
    text = answer_from_knowledge("退款政策")
    assert "support-policy.md" in text


def test_knowledge_dir_from_settings() -> None:
    settings = get_settings()
    assert settings.knowledge_dir.is_dir()
    assert (settings.knowledge_dir / "support-policy.md").is_file()
