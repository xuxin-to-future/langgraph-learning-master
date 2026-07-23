"""HTTP / 工单 DTO（Pydantic）。

对外 JSON 使用 sessionId；对内 session_id → LangGraph thread_id。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from customer_service.models.state import Intent
from customer_service.services.tickets import PROBLEM_TYPE_OPTIONS, RATING_LABELS

ProblemType = Literal["业务问题", "系统 Bug", "个人反馈", "功能建议", "其他"]


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
    needs_ticket_form: bool = Field(default=False, alias="needsTicketForm")
    session_reset: bool = Field(default=False, alias="sessionReset")
    turn_type: str | None = Field(default=None, alias="turnType")
    need_retrieve: bool | None = Field(default=None, alias="needRetrieve")
    citations: list[str] = Field(default_factory=list)
    error: str | None = None


class TicketCreate(BaseModel):
    """创建工单时的内部/管理入参（兼容旧字段）。"""

    subject: str = Field(..., min_length=1)
    description: str = ""
    session_id: str | None = Field(default=None, alias="sessionId")

    model_config = ConfigDict(populate_by_name=True)


class TicketFormCreate(BaseModel):
    """POST /v1/tickets 表单建单请求。"""

    model_config = ConfigDict(populate_by_name=True)

    problem_types: list[str] = Field(..., min_length=1, alias="problemTypes")
    description: str = Field(..., min_length=1)
    rating: int = Field(..., ge=1, le=5)
    attachments: list[str] = Field(default_factory=list)
    session_id: str | None = Field(default=None, alias="sessionId")
    reporter: str = "admin"

    @field_validator("problem_types")
    @classmethod
    def _validate_types(cls, value: list[str]) -> list[str]:
        cleaned = [v.strip() for v in value if (v or "").strip()]
        if not cleaned:
            raise ValueError("至少选择一个问题类型")
        unknown = [v for v in cleaned if v not in PROBLEM_TYPE_OPTIONS]
        if unknown:
            raise ValueError(f"非法问题类型: {', '.join(unknown)}")
        # 去重且保序
        seen: set[str] = set()
        out: list[str] = []
        for item in cleaned:
            if item not in seen:
                seen.add(item)
                out.append(item)
        return out

    @field_validator("description")
    @classmethod
    def _validate_description(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError("问题描述不能为空")
        return text

    @field_validator("rating")
    @classmethod
    def _validate_rating(cls, value: int) -> int:
        if value not in RATING_LABELS:
            raise ValueError("评分须为 1-5")
        return value

    @field_validator("attachments")
    @classmethod
    def _validate_attachments(cls, value: list[str]) -> list[str]:
        urls = [u.strip() for u in value if (u or "").strip()]
        if len(urls) > 3:
            raise ValueError("最多上传 3 张图片")
        return urls


class TicketAttachmentResponse(BaseModel):
    """附件上传响应。"""

    model_config = ConfigDict(populate_by_name=True)

    url: str


class TicketResponse(BaseModel):
    """工单查询响应。"""

    model_config = ConfigDict(populate_by_name=True)

    ticket_id: str
    subject: str
    description: str = ""
    status: str = "open"
    session_id: str | None = Field(default=None, alias="sessionId")
    created_at: datetime | None = None
    problem_types: list[str] = Field(default_factory=list, alias="problemTypes")
    attachments: list[str] = Field(default_factory=list)
    rating: int | None = None
    rating_label: str | None = Field(default=None, alias="ratingLabel")
    reporter: str = "admin"


class EscalateResumeRequest(BaseModel):
    """POST /v1/admin/escalate/{sessionId}/resume 请求体。"""

    message: str = Field(
        default="已处理",
        description="人工回复或处理说明，将作为 resume 载荷",
    )
    approve: bool = True
