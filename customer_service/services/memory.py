"""会话记忆 / Checkpointer 工厂。

约定（Task 4.2，供 API 层遵守）：

- 对外 HTTP 字段：`sessionId`（JSON）/ `session_id`（Python）
- LangGraph 调用：`config={"configurable": {"thread_id": session_id}}`
- **同一用户会话必须使用相同 `sessionId`**，才能读写同一条 checkpoint 线程
- 推荐使用 `thread_config(session_id)` 生成 config，避免手写字段名出错

后端选择：

- 默认 `CHECKPOINTER_BACKEND=memory` → `MemorySaver`（进程内，重启丢失）
- `CHECKPOINTER_BACKEND=sqlite` → `SqliteSaver`（文件 `CHECKPOINTER_SQLITE_PATH`）
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from langgraph.checkpoint.memory import MemorySaver

from customer_service.config.settings import get_settings

# 保持 Sqlite 连接存活，避免每次请求新建
_sqlite_conn: sqlite3.Connection | None = None
_sqlite_saver: Any | None = None


def thread_config(session_id: str) -> dict[str, Any]:
    """将对外 sessionId 映射为 LangGraph configurable.thread_id。"""
    sid = (session_id or "").strip()
    if not sid:
        raise ValueError("session_id is required for checkpoint thread")
    return {"configurable": {"thread_id": sid}}


def get_checkpointer(*, persist: bool | None = None) -> Any:
    """返回 Checkpointer。

    Args:
        persist: True 强制 SqliteSaver；False 强制 MemorySaver；
                 None 时跟随 settings.checkpointer_backend。
    """
    settings = get_settings()
    if persist is None:
        use_sqlite = settings.checkpointer_backend == "sqlite"
    else:
        use_sqlite = persist

    if use_sqlite:
        return _get_sqlite_saver(settings.checkpointer_sqlite_path)
    return MemorySaver()


def _get_sqlite_saver(db_path: Path) -> Any:
    global _sqlite_conn, _sqlite_saver

    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "使用 SqliteSaver 需要安装：pip install langgraph-checkpoint-sqlite"
        ) from exc

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    resolved = str(path.resolve())

    if _sqlite_saver is not None and _sqlite_conn is not None:
        # 路径变更时重建
        try:
            current = _sqlite_conn.execute("PRAGMA database_list").fetchone()
            current_path = Path(current[2]).resolve() if current and current[2] else None
            if current_path == path.resolve():
                return _sqlite_saver
        except sqlite3.Error:
            pass

    conn = sqlite3.connect(resolved, check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()
    _sqlite_conn = conn
    _sqlite_saver = saver
    return saver


def reset_checkpointer_cache() -> None:
    """测试用：关闭并清空 Sqlite checkpointer 缓存。"""
    global _sqlite_conn, _sqlite_saver
    if _sqlite_conn is not None:
        try:
            _sqlite_conn.close()
        except sqlite3.Error:
            pass
    _sqlite_conn = None
    _sqlite_saver = None
