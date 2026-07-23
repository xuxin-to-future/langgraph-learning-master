"""工单与管理辅助路由。

POST /v1/tickets
POST /v1/tickets/attachments
GET  /v1/tickets/{ticket_id}
POST /v1/admin/escalate/{sessionId}/resume
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from langgraph.types import Command

from customer_service.api.mapping import (
    graph_result_to_chat_response,
    ticket_row_to_response,
)
from customer_service.models.schemas import (
    ChatResponse,
    EscalateResumeRequest,
    TicketAttachmentResponse,
    TicketFormCreate,
    TicketResponse,
)
from customer_service.services import tickets as ticket_service
from customer_service.services.memory import thread_config
from customer_service.services.oss import (
    MAX_ATTACHMENT_BYTES,
    upload_ticket_image,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])


@router.post("/v1/tickets", response_model=TicketResponse)
def create_ticket(body: TicketFormCreate) -> TicketResponse:
    """表单创建工单；提交人固定 admin（暂无登录）。"""
    try:
        ticket_id = ticket_service.create_ticket(
            description=body.description,
            session_id=body.session_id,
            problem_types=body.problem_types,
            attachments=body.attachments,
            rating=body.rating,
            reporter="admin",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        logger.exception("create ticket failed")
        raise HTTPException(status_code=500, detail="工单创建失败，请稍后重试") from None

    row = ticket_service.get_ticket(ticket_id)
    if row is None:
        raise HTTPException(status_code=500, detail="工单创建后查询失败")
    return ticket_row_to_response(row)


@router.post("/v1/tickets/attachments", response_model=TicketAttachmentResponse)
async def upload_ticket_attachment(
    file: UploadFile = File(...),
) -> TicketAttachmentResponse:
    """上传工单图片附件到 OSS。"""
    content_type = file.content_type or "application/octet-stream"
    data = await file.read()
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"单张图片不能超过 {MAX_ATTACHMENT_BYTES // (1024 * 1024)}MB",
        )
    try:
        url = upload_ticket_image(
            data=data,
            filename=file.filename,
            content_type=content_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.exception("oss upload failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception:
        logger.exception("oss upload unexpected error")
        raise HTTPException(status_code=502, detail="附件上传失败，请稍后重试") from None
    return TicketAttachmentResponse(url=url)


@router.get("/v1/tickets/{ticket_id}", response_model=TicketResponse)
def get_ticket(ticket_id: str) -> TicketResponse:
    row = ticket_service.get_ticket(ticket_id)
    if row is None:
        raise HTTPException(status_code=404, detail="工单不存在")
    return ticket_row_to_response(row)


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
