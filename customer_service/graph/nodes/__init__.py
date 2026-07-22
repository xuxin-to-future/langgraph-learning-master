"""图节点集合。"""

from customer_service.graph.nodes.chitchat import chitchat_node
from customer_service.graph.nodes.escalate import escalate_node
from customer_service.graph.nodes.faq import faq_node
from customer_service.graph.nodes.supervisor import (
    classify_intent_by_rules,
    supervisor_node,
)
from customer_service.graph.nodes.ticket import ticket_node

__all__ = [
    "chitchat_node",
    "classify_intent_by_rules",
    "escalate_node",
    "faq_node",
    "supervisor_node",
    "ticket_node",
]
