"""转人工工具。"""

from __future__ import annotations

from typing import Any


def request_human_handoff(reason: str, session_id: str = "") -> dict[str, Any]:
    """构造转人工载荷（供 interrupt 使用，不直接发外部系统）。"""
    return {
        "type": "escalate",
        "reason": (reason or "").strip() or "用户请求人工",
        "session_id": session_id or None,
        "prompt": "已转人工，请运营人员处理后调用 resume 接口。",
        "needs_human": True,
    }
