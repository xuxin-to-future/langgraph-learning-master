"""客服测试公共夹具。"""

from __future__ import annotations

import pytest

from customer_service.config.settings import get_settings


@pytest.fixture(autouse=True)
def _force_local_rag_provider(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RAG_PROVIDER", "local")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def acceptance_intent(text: str, *args, **kwargs) -> str:
    """测试替身：模拟 LLM 对验收话术的分类结果（非生产关键词路由）。"""
    _ = args, kwargs
    t = (text or "").strip()
    if any(k in t for k in ("投诉", "人工", "客服", "找人", "经理", "律师")):
        return "escalate"
    if any(
        k in t
        for k in (
            "工单",
            "无法登录",
            "登不上",
            "开单",
            "报修",
            "故障",
            "吐槽",
            "反馈",
            "烂系统",
            "傻逼系统",
            "卡死",
            "报错",
        )
    ):
        return "ticket"
    if any(k in t for k in ("退款", "政策", "计费", "怎么用", "功能", "套餐", "价格")):
        return "faq"
    return "chitchat"


@pytest.fixture()
def mock_intent_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """集成测试不打真实 LLM：伪造意图分类 + 会话分析。"""

    class _S:
        has_openai_key = True
        allow_offline_fallback = True
        openai_api_key = "sk-test"
        openai_model = "dummy"
        openai_base_url = None
        session_context_token_budget = 3500

    monkeypatch.setattr(
        "customer_service.graph.nodes.supervisor.get_settings",
        lambda: _S(),
    )
    monkeypatch.setattr(
        "customer_service.graph.nodes.supervisor._classify_intent_by_llm",
        lambda text, session_block="", turn_type="": acceptance_intent(text),
    )

    from customer_service.services.session_analyze import SessionAnalyzeResult
    from customer_service.services.session_memory import (
        heuristic_session_update,
        normalize_session_memory,
    )

    def _fake_analyze(
        user_text: str,
        *,
        prompt_block: str = "",
        memory=None,
        has_history: bool = False,
    ) -> SessionAnalyzeResult:
        fb = heuristic_session_update(
            user_text,
            normalize_session_memory(memory),
            has_history=has_history
            or bool(prompt_block and ("用户：" in prompt_block or "助手：" in prompt_block)),
        )
        return SessionAnalyzeResult(
            turn_type=fb["turn_type"],
            need_retrieve=fb["need_retrieve"],
            standalone_query=fb["standalone_query"],
            session_memory=fb["session_memory"],
        )

    monkeypatch.setattr(
        "customer_service.graph.nodes.session.analyze_turn",
        _fake_analyze,
    )
    monkeypatch.setattr(
        "customer_service.graph.nodes.session.prepare_session_update",
        lambda _state: {},
    )
