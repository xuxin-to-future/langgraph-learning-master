"""Supervisor：意图路由节点（仅 LLM 分类，每轮单一意图）。"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path

from customer_service.config.settings import get_settings
from customer_service.graph.nodes._message_utils import (
    last_user_text,
    session_context_from_state,
)
from customer_service.models.state import Intent, SupportState

logger = logging.getLogger(__name__)

_VALID: tuple[Intent, ...] = ("faq", "ticket", "chitchat", "escalate")
_PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "supervisor.md"


@lru_cache(maxsize=1)
def load_supervisor_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _parse_intent_label(raw: str) -> Intent | None:
    """从模型输出中解析唯一意图标签。"""
    text = (raw or "").strip()
    if not text:
        return None

    try:
        data = json.loads(text)
        if isinstance(data, str) and data.strip().lower() in _VALID:
            return data.strip().lower()  # type: ignore[return-value]
        if isinstance(data, dict):
            val = str(data.get("intent") or data.get("label") or "").strip().lower()
            if val in _VALID:
                return val  # type: ignore[return-value]
    except json.JSONDecodeError:
        pass

    first = text.splitlines()[0].strip().lower()
    first = first.strip("`\"'。．.：: ")
    if first in _VALID:
        return first  # type: ignore[return-value]

    for intent in ("escalate", "ticket", "chitchat", "faq"):
        if re.search(rf"(?<![a-z]){intent}(?![a-z])", text.lower()):
            return intent  # type: ignore[return-value]
    return None


def _classify_intent_by_llm(
    text: str,
    *,
    session_block: str = "",
    turn_type: str = "",
) -> Intent | None:
    """使用规范提示词调用模型做意图分类。"""
    settings = get_settings()
    if not settings.has_openai_key:
        return None

    history = ""
    if (session_block or "").strip():
        history = f"## 会话上下文（供理解指代，不要据此输出多个标签）\n{session_block.strip()}\n\n"

    turn_hint = ""
    if (turn_type or "").strip():
        turn_hint = f"- 会话层 turn_type={turn_type.strip()}（仅供参考；session_recall 请标 chitchat）\n"

    user_block = (
        f"{history}"
        "## 待分类的用户本轮消息\n"
        f"{text.strip()}\n\n"
        "## 要求\n"
        "- 只能四选一，互斥，不要解释\n"
        f"{turn_hint}"
        "- 吐槽/骂系统/报障 → ticket\n"
        "- 明确找人/投诉对接 → escalate\n"
        "- 问政策/功能/价格或对上文的追问 → faq\n"
        "- 寒暄、会话回忆（刚才问了什么）或无关闲聊 → chitchat\n\n"
        "## 你的输出\n"
        "只输出一个标签：faq / ticket / chitchat / escalate"
    )

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
                SystemMessage(content=load_supervisor_prompt()),
                HumanMessage(content=user_block),
            ]
        )
        raw = str(getattr(resp, "content", "") or "")
        intent = _parse_intent_label(raw)
        if intent is None:
            logger.warning("supervisor LLM 输出无法解析: %r", raw[:200])
        return intent
    except Exception:
        logger.exception("supervisor LLM 调用失败")
        return None


def classify_intent(
    text: str,
    *,
    session_block: str = "",
    turn_type: str = "",
) -> Intent:
    """生产路径：只走 LLM。无 Key 或失败时回退 chitchat。"""
    if (turn_type or "").strip() == "session_recall":
        return "chitchat"

    settings = get_settings()
    if not settings.has_openai_key:
        logger.error("未配置 OPENAI_API_KEY，无法进行意图分类，回退 chitchat")
        return "chitchat"

    llm_intent = _classify_intent_by_llm(
        text, session_block=session_block, turn_type=turn_type
    )
    if llm_intent is not None:
        return llm_intent

    logger.error("意图分类失败，回退 chitchat")
    return "chitchat"


def supervisor_node(state: SupportState) -> dict:
    """每轮：重置表单/转人工标志；输出唯一业务意图（压缩已在 session 节点完成）。"""
    text = last_user_text(state)
    ctx = session_context_from_state(state)
    turn_type = str(state.get("turn_type") or "")
    intent = classify_intent(
        text, session_block=ctx.prompt_block, turn_type=turn_type
    )
    return {
        "intent": intent,
        "needs_ticket_form": False,
        "needs_human": False,
    }
