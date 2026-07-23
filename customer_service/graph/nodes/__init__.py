"""图节点集合。"""

from customer_service.graph.nodes.chitchat import chitchat_node
from customer_service.graph.nodes.escalate import escalate_node
from customer_service.graph.nodes.faq import faq_node
from customer_service.graph.nodes.session import session_node
from customer_service.graph.nodes.supervisor import classify_intent, supervisor_node
from customer_service.graph.nodes.ticket import ticket_node

__all__ = [
    "chitchat_node",
    "classify_intent",
    "escalate_node",
    "faq_node",
    "session_node",
    "supervisor_node",
    "ticket_node",
]
