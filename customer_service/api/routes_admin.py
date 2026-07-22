"""管理辅助路由。

GET /v1/tickets/{ticket_id}
POST /v1/admin/escalate/{sessionId}/resume
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from langgraph.types import Command

from customer_service.api.mapping import (
    graph_result_to_chat_response,
    parse_ticket_created_at,
)
from customer_service.models.schemas import (
    ChatResponse,
    EscalateResumeRequest,
    TicketResponse,
)
from customer_service.services import tickets as ticket_service
from customer_service.services.memory import thread_config

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])


@router.get("/v1/tickets/{ticket_id}", response_model=TicketResponse)
def get_ticket(ticket_id: str) -> TicketResponse:
    row = ticket_service.get_ticket(ticket_id)
    if row is None:
        raise HTTPException(status_code=404, detail="工单不存在")
    return TicketResponse(
        ticket_id=row["ticket_id"],
        subject=row["subject"],
        description=row.get("description") or "",
        status=row.get("status") or "open",
        sessionId=row.get("session_id"),
        created_at=parse_ticket_created_at(row.get("created_at")),
    )


@router.post(
    "/v1/admin/escalate/{session_id}/resume",
    response_model=ChatResponse,
)
def resume_escalate(
    session_id: str,
    body: EscalateResumeRequest,
    request: Request,
) -> ChatResponse:
    """人工处理后 resume 同一 thread（sessionId == thread_id）。"""
    sid = (session_id or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="sessionId 不能为空")

    graph = request.app.state.graph
    config = thread_config(sid)
    resume_payload = {
        "message": body.message,
        "approve": body.approve,
    }

    try:
        # 与图内 interrupt() 对应：Command(resume=...) + 同一 thread_id
        result = graph.invoke(Command(resume=resume_payload), config)
    except Exception:
        logger.exception("resume failed session_id=%s", sid)
        raise HTTPException(
            status_code=502,
            detail="恢复会话失败：可能未处于等待人工状态，或会话已过期",
        ) from None

    return graph_result_to_chat_response(sid, result)
