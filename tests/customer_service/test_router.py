"""supervisor 路由测试占位。"""

from __future__ import annotations

import pytest

from customer_service.graph.edges import route_by_intent


def test_route_by_intent_requires_intent() -> None:
    with pytest.raises(ValueError):
        route_by_intent({})


def test_route_by_intent_returns_intent() -> None:
    assert route_by_intent({"intent": "faq"}) == "faq"
