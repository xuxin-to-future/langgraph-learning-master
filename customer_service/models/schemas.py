"""HTTP / 工单 DTO（Pydantic）。

对外 JSON 使用 sessionId；对内 session_id → LangGraph thread_id。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from customer_service.models.state import Intent


class ChatRequest(BaseModel):
    """POST /v1/chat 请求体。"""

    model_config = ConfigDict(populate_by_name=True)

    session_id: str = Field(..., min_length=1, alias="sessionId")
    message: str = Field(..., min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    """POST /v1/chat 响应体。"""

    model_config = ConfigDict(populate_by_name=True)

    session_id: str = Field(..., alias="sessionId")
    intent: Intent
    answer: str
    ticket_id: str | None = None
    needs_human: bool = False
    citations: list[str] = Field(default_factory=list)
    error: str | None = None


class TicketCreate(BaseModel):
    """创建工单时的内部/管理入参（非必须暴露为 HTTP）。"""

    subject: str = Field(..., min_length=1)
    description: str = ""
    session_id: str | None = Field(default=None, alias="sessionId")

    model_config = ConfigDict(populate_by_name=True)


class TicketResponse(BaseModel):
    """工单查询响应。"""

    model_config = ConfigDict(populate_by_name=True)

    ticket_id: str
    subject: str
    description: str = ""
    status: str = "open"
    session_id: str | None = Field(default=None, alias="sessionId")
    created_at: datetime | None = None


class EscalateResumeRequest(BaseModel):
    """POST /v1/admin/escalate/{sessionId}/resume 请求体。"""

    message: str = Field(
        default="已处理",
        description="人工回复或处理说明，将作为 resume 载荷",
    )
    approve: bool = True
