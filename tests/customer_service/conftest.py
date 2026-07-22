"""客服测试默认强制本地 RAG，避免依赖外网 / 本机 8100。"""

from __future__ import annotations

import pytest

from customer_service.config.settings import get_settings


@pytest.fixture(autouse=True)
def _force_local_rag_provider(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RAG_PROVIDER", "local")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
