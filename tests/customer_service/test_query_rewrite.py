"""多轮检索问句改写单测。"""

from __future__ import annotations

from customer_service.services.rag import _heuristic_rewrite, rewrite_retrieval_query


def test_heuristic_rewrite_prepends_last_user_topic() -> None:
    history = (
        "## 最近对话\n"
        "用户：商机周期是什么？\n"
        "助手：商机有效期为 90 天……\n"
        "用户：整理成计算公式"
    )
    out = _heuristic_rewrite("整理成计算公式", history)
    assert "商机周期" in out
    assert "整理成计算公式" in out


def test_rewrite_falls_back_without_history(monkeypatch) -> None:
    monkeypatch.setattr(
        "customer_service.services.rag.get_settings",
        lambda: type("S", (), {"has_openai_key": False})(),
    )
    assert rewrite_retrieval_query("退款政策是什么？", "") == "退款政策是什么？"
