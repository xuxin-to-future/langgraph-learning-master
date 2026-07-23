"""session 分析 JSON 解析与降级单测。"""

from __future__ import annotations

from customer_service.services.session_analyze import parse_analyze_payload
from customer_service.services.session_memory import empty_session_memory


def test_parse_analyze_payload_followup() -> None:
    mem = empty_session_memory()
    mem["topic"] = "商机"
    result = parse_analyze_payload(
        {
            "turn_type": "followup",
            "need_retrieve": True,
            "standalone_query": "商机周期整理成计算公式",
            "memory": {"topic": "商机周期", "entities": ["商机"]},
        },
        user_text="整理成计算公式",
        memory=mem,
        has_history=True,
    )
    assert result.turn_type == "followup"
    assert result.need_retrieve is True
    assert "商机" in result.standalone_query
    assert result.session_memory["topic"] == "商机周期"


def test_parse_forces_no_retrieve_on_recall() -> None:
    result = parse_analyze_payload(
        {
            "turn_type": "session_recall",
            "need_retrieve": True,
            "standalone_query": "我刚才问的是什么",
            "memory": {},
        },
        user_text="我刚才问的是什么",
        memory=empty_session_memory(),
        has_history=True,
    )
    assert result.turn_type == "session_recall"
    assert result.need_retrieve is False
