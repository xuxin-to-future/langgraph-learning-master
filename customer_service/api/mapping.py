"""将图运行结果映射为 API 响应。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from customer_service.models.schemas import ChatResponse, TicketResponse
from customer_service.models.state import Intent
from customer_service.services.tickets import RATING_LABELS


def citations_from_docs(docs: list[str] | None) -> list[str]:
    out: list[str] = []
    for doc in docs or []:
        if doc.startswith("[") and "]" in doc:
            src = doc[1 : doc.index("]")]
            if src and src not in out:
                out.append(src)
    return out


def graph_result_to_chat_response(session_id: str, result: dict[str, Any]) -> ChatResponse:
    """把 graph.invoke 结果转为 ChatResponse；含 interrupt 时 needs_human=true。"""
    interrupts = result.get("__interrupt__")
    if interrupts:
        first = interrupts[0]
        payload = getattr(first, "value", first)
        if isinstance(payload, dict):
            answer = str(
                payload.get("prompt")
                or payload.get("reason")
                or "已转人工，请等待客服处理。"
            )
        else:
            answer = "已转人工，请等待客服处理。"
        intent: Intent = result.get("intent") or "escalate"
        return ChatResponse(
            sessionId=session_id,
            intent=intent,
            answer=answer,
            ticket_id=result.get("ticket_id"),
            needs_human=True,
            needsTicketForm=False,
            sessionReset=False,
            turnType=result.get("turn_type"),
            needRetrieve=result.get("need_retrieve"),
            citations=citations_from_docs(result.get("retrieved_docs")),
            error=result.get("error"),
        )

    intent = result.get("intent")
    if intent is None:
        intent = "chitchat"

    # 表单仅随本轮 ticket 意图出现，杜绝跨轮状态串扰
    needs_form = intent == "ticket"
    return ChatResponse(
        sessionId=session_id,
        intent=intent,
        answer=result.get("answer") or "",
        ticket_id=None if needs_form else result.get("ticket_id"),
        needs_human=bool(result.get("needs_human")) and intent == "escalate",
        needsTicketForm=needs_form,
        sessionReset=bool(result.get("session_reset")),
        turnType=result.get("turn_type"),
        needRetrieve=result.get("need_retrieve"),
        citations=[] if needs_form else citations_from_docs(result.get("retrieved_docs")),
        error=result.get("error"),
    )


def parse_ticket_created_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def ticket_row_to_response(row: dict[str, Any]) -> TicketResponse:
    rating = row.get("rating")
    label = RATING_LABELS.get(rating) if isinstance(rating, int) else None
    return TicketResponse(
        ticket_id=row["ticket_id"],
        subject=row["subject"],
        description=row.get("description") or "",
        status=row.get("status") or "open",
        sessionId=row.get("session_id"),
        created_at=parse_ticket_created_at(row.get("created_at")),
        problemTypes=list(row.get("problem_types") or []),
        attachments=list(row.get("attachments") or []),
        rating=rating,
        ratingLabel=label,
        reporter=row.get("reporter") or "admin",
    )
