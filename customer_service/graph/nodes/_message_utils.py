"""从 SupportState.messages 提取最近一条用户文本。"""

from __future__ import annotations

from typing import Any

from customer_service.models.state import SupportState


def last_user_text(state: SupportState) -> str:
    messages = state.get("messages") or []
    for msg in reversed(messages):
        text = _message_content(msg)
        if not text:
            continue
        role = _message_role(msg)
        if role in {"human", "user", None}:
            # 无明确角色时，取最后一条非空文本兜底
            if role is not None or msg is messages[-1]:
                return text
    # 兜底：最后一条任意消息
    if messages:
        return _message_content(messages[-1])
    return ""


def _message_role(msg: Any) -> str | None:
    if isinstance(msg, dict):
        t = msg.get("type") or msg.get("role")
        return str(t).lower() if t is not None else None
    t = getattr(msg, "type", None)
    return str(t).lower() if t is not None else None


def _message_content(msg: Any) -> str:
    if isinstance(msg, dict):
        content = msg.get("content", "")
    else:
        content = getattr(msg, "content", "")
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts).strip()
    return str(content or "").strip()
