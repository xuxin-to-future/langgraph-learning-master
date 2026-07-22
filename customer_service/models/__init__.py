"""领域模型与 API 契约。"""

from customer_service.models.schemas import (
    ChatRequest,
    ChatResponse,
    EscalateResumeRequest,
    TicketCreate,
    TicketResponse,
)
from customer_service.models.state import Intent, SupportState

__all__ = [
    "ChatRequest",
    "ChatResponse",
    "EscalateResumeRequest",
    "Intent",
    "SupportState",
    "TicketCreate",
    "TicketResponse",
]
