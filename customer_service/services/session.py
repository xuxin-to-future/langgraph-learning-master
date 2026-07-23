"""会话管理：新会话识别、token 计量、上下文窗口与超预算压缩。"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Sequence

from customer_service.config.settings import get_settings

logger = logging.getLogger(__name__)

# 整句匹配（去首尾空白、全角符号后）
_NEW_SESSION_EXACT = {
    "/new",
    "/reset",
    "新会话",
    "新建会话",
    "重新开始",
    "清空对话",
    "开启新会话",
    "换个话题重新聊",
}

_NEW_SESSION_RE = re.compile(
    r"^\s*(?:/new|/reset|新会话|新建会话|重新开始|清空对话|开启新会话)\s*[。.!！？?]*\s*$",
    re.IGNORECASE,
)


def is_new_session_command(text: str) -> bool:
    """用户是否在请求开启新会话（优先于意图路由）。"""
    raw = (text or "").strip()
    if not raw:
        return False
    normalized = raw.lower().replace("　", " ").strip()
    if normalized in _NEW_SESSION_EXACT or raw in _NEW_SESSION_EXACT:
        return True
    return bool(_NEW_SESSION_RE.match(raw))


def new_session_id() -> str:
    return str(uuid.uuid4())


@lru_cache(maxsize=1)
def _encoding():
    try:
        import tiktoken

        return tiktoken.get_encoding("cl100k_base")
    except Exception:  # noqa: BLE001
        return None


def count_tokens(text: str) -> int:
    """估算 token；tiktoken 不可用时按 ~2 字/token 退化。"""
    s = text or ""
    enc = _encoding()
    if enc is None:
        return max(1, (len(s) + 1) // 2) if s else 0
    try:
        return len(enc.encode(s))
    except Exception:  # noqa: BLE001
        return max(1, (len(s) + 1) // 2) if s else 0


def _message_role(msg: Any) -> str:
    if isinstance(msg, dict):
        t = msg.get("type") or msg.get("role")
    else:
        t = getattr(msg, "type", None) or getattr(msg, "role", None)
    role = str(t or "").lower()
    if role in {"human", "user"}:
        return "user"
    if role in {"ai", "assistant"}:
        return "assistant"
    if role in {"system"}:
        return "system"
    return "other"


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


def iter_dialogue_turns(messages: Sequence[Any]) -> list[tuple[str, str]]:
    """提取 user/assistant 对话轮次（跳过空内容）。"""
    turns: list[tuple[str, str]] = []
    for msg in messages or []:
        role = _message_role(msg)
        if role not in {"user", "assistant"}:
            continue
        text = _message_content(msg)
        if text:
            turns.append((role, text))
    return turns


def format_turns_for_prompt(turns: Sequence[tuple[str, str]]) -> str:
    lines: list[str] = []
    for role, text in turns:
        label = "用户" if role == "user" else "助手"
        lines.append(f"{label}：{text}")
    return "\n".join(lines)


@dataclass(frozen=True)
class SessionContext:
    """供各节点消费的会话上下文。"""

    summary: str
    recent_turns: list[tuple[str, str]]
    prompt_block: str
    token_count: int


def build_session_context(
    messages: Sequence[Any],
    *,
    summary: str = "",
    token_budget: int | None = None,
) -> SessionContext:
    """按 token 预算裁剪：保留摘要 + 从尾部往前装入的最近对话。"""
    settings = get_settings()
    budget = (
        token_budget
        if token_budget is not None
        else getattr(settings, "session_context_token_budget", 3500)
    )
    budget = max(512, int(budget))
    summary_text = (summary or "").strip()
    turns = iter_dialogue_turns(messages)

    summary_tokens = count_tokens(summary_text) if summary_text else 0
    remaining = max(0, budget - summary_tokens - (16 if summary_text else 0))

    kept_rev: list[tuple[str, str]] = []
    used = 0
    for role, text in reversed(turns):
        piece = f"{role}:{text}"
        cost = count_tokens(piece) + 4
        if kept_rev and used + cost > remaining:
            break
        if not kept_rev and cost > remaining:
            # 至少保留最后一条（截断文本）
            trim = text
            while trim and count_tokens(trim) + 4 > remaining:
                trim = trim[: max(0, len(trim) // 2)]
            if trim:
                kept_rev.append((role, trim))
            break
        kept_rev.append((role, text))
        used += cost

    recent = list(reversed(kept_rev))
    parts: list[str] = []
    if summary_text:
        parts.append(f"## 会话摘要\n{summary_text}")
    if recent:
        parts.append("## 最近对话\n" + format_turns_for_prompt(recent))
    prompt_block = "\n\n".join(parts).strip()
    return SessionContext(
        summary=summary_text,
        recent_turns=recent,
        prompt_block=prompt_block,
        token_count=count_tokens(prompt_block),
    )


def needs_compression(
    messages: Sequence[Any],
    *,
    summary: str = "",
    token_budget: int | None = None,
) -> bool:
    """全部对话（非仅窗口）是否超过预算，需要把旧轮次压进摘要。"""
    settings = get_settings()
    budget = (
        token_budget
        if token_budget is not None
        else getattr(settings, "session_context_token_budget", 3500)
    )
    turns = iter_dialogue_turns(messages)
    full = ""
    if (summary or "").strip():
        full += f"摘要：{(summary or '').strip()}\n"
    full += format_turns_for_prompt(turns)
    return count_tokens(full) > max(512, int(budget))


def compress_session(
    messages: Sequence[Any],
    *,
    summary: str = "",
    token_budget: int | None = None,
) -> str:
    """将超出预算的旧对话压进 summary；失败时用截断拼接降级。"""
    settings = get_settings()
    budget = (
        token_budget
        if token_budget is not None
        else getattr(settings, "session_context_token_budget", 3500)
    )
    budget = max(512, int(budget))
    turns = iter_dialogue_turns(messages)
    if not turns:
        return (summary or "").strip()

    # 先按预算留下尾部，头部送去摘要
    ctx = build_session_context(messages, summary="", token_budget=budget)
    keep_n = len(ctx.recent_turns)
    older = turns[:-keep_n] if keep_n < len(turns) else []
    if not older and not needs_compression(messages, summary=summary, token_budget=budget):
        return (summary or "").strip()

    older_text = format_turns_for_prompt(older)
    prev = (summary or "").strip()
    merged_source = ""
    if prev:
        merged_source += f"既有摘要：\n{prev}\n\n"
    if older_text:
        merged_source += f"需压缩的更早对话：\n{older_text}"

    if not merged_source.strip():
        return prev

    llm_summary = _summarize_with_llm(merged_source)
    if llm_summary:
        return llm_summary

    # 无 Key / 失败：截断拼接
    fallback = (prev + "\n" + older_text).strip() if prev else older_text
    while fallback and count_tokens(fallback) > budget // 2:
        fallback = fallback[len(fallback) // 4 :]
    return fallback.strip()


def _summarize_with_llm(source: str) -> str | None:
    settings = get_settings()
    if not settings.has_openai_key:
        return None
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            temperature=0,
        )
        resp = llm.invoke(
            [
                SystemMessage(
                    content=(
                        "你是会话摘要器。将对话压成简洁中文摘要，保留："
                        "用户问题要点、已确认事实、未决事项、关键实体。"
                        "去掉寒暄与重复。只输出摘要正文，不要标题。"
                    )
                ),
                HumanMessage(content=source[:12000]),
            ]
        )
        text = str(getattr(resp, "content", "") or "").strip()
        return text or None
    except Exception:
        logger.exception("session summarize failed")
        return None


def prepare_session_update(state: dict[str, Any]) -> dict[str, Any]:
    """供 supervisor 调用：必要时更新 conversation_summary。"""
    messages = state.get("messages") or []
    summary = str(state.get("conversation_summary") or "")
    if not needs_compression(messages, summary=summary):
        return {}
    new_summary = compress_session(messages, summary=summary)
    if new_summary == summary:
        return {}
    logger.info(
        "session compressed summary_tokens=%s",
        count_tokens(new_summary),
    )
    return {"conversation_summary": new_summary}
