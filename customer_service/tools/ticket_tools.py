"""工单相关工具（供图节点 / LLM 调用的薄封装）。"""

from __future__ import annotations

from typing import Any

from customer_service.services import tickets as ticket_service


def create_ticket_tool(
    subject: str,
    description: str = "",
    session_id: str = "",
) -> str:
    """创建工单并返回 ticket_id。"""
    return ticket_service.create_ticket(
        subject=subject,
        description=description,
        session_id=session_id or None,
    )


def get_ticket_tool(ticket_id: str) -> dict[str, Any] | None:
    """查询工单；不存在返回 None。"""
    return ticket_service.get_ticket(ticket_id)
