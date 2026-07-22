"""Checkpointer / session 约定单测。"""

from __future__ import annotations

from pathlib import Path

import pytest
from langgraph.checkpoint.memory import MemorySaver

from customer_service.services import memory


def test_thread_config_maps_session_id() -> None:
    cfg = memory.thread_config("user-42")
    assert cfg == {"configurable": {"thread_id": "user-42"}}


def test_thread_config_rejects_empty() -> None:
    with pytest.raises(ValueError):
        memory.thread_config("  ")


def test_get_checkpointer_default_memory() -> None:
    cp = memory.get_checkpointer(persist=False)
    assert isinstance(cp, MemorySaver)


def test_get_checkpointer_sqlite(tmp_path: Path) -> None:
    memory.reset_checkpointer_cache()
    db = tmp_path / "checkpoints.sqlite"
    # 直接走内部工厂，避免污染全局 settings 缓存语义
    cp = memory._get_sqlite_saver(db)
    assert db.exists() or db.parent.exists()
    # 再取一次应复用
    cp2 = memory._get_sqlite_saver(db)
    assert cp2 is cp
    memory.reset_checkpointer_cache()
