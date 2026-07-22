"""Supervisor：意图路由节点（模型优先，规则仅作离线降级）。"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path

from customer_service.config.settings import get_settings
from customer_service.graph.nodes._message_utils import last_user_text
from customer_service.models.state import Intent, SupportState

logger = logging.getLogger(__name__)

_VALID: tuple[Intent, ...] = ("faq", "ticket", "chitchat", "escalate")
_PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "supervisor.md"

# 仅无 Key / 模型失败时的离线降级（非主路径）
_ESCALATE_KW = ("投诉", "人工", "客服", "找人", "经理", "律师")
_TICKET_KW = ("工单", "无法登录", "登不上", "开单", "报修", "故障单", "建一个")
_FAQ_KW = ("退款", "政策", "计费", "怎么用", "功能", "套餐", "价格", "发票", "支持")


@lru_cache(maxsize=1)
def load_supervisor_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def classify_intent_by_rules(text: str) -> Intent:
    """离线降级：关键词分类（主路径应使用模型）。"""
    t = (text or "").strip()
    if any(k in t for k in _ESCALATE_KW):
        return "escalate"
    if any(k in t for k in _TICKET_KW):
        return "ticket"
    if any(k in t for k in _FAQ_KW):
        return "faq"
    return "chitchat"


def _parse_intent_label(raw: str) -> Intent | None:
    """从模型输出中解析唯一意图标签。"""
    text = (raw or "").strip()
    if not text:
        return None

    # 尝试 JSON：{"intent":"faq"} 或 "faq"
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

    # 取首行，去掉常见包裹
    first = text.splitlines()[0].strip().lower()
    first = first.strip("`\"'。．.：: ")
    if first in _VALID:
        return first  # type: ignore[return-value]

    # 整段仅为标签附近时，用词边界匹配（避免误伤长文）
    for intent in ("escalate", "ticket", "chitchat", "faq"):
        if re.search(rf"(?<![a-z]){intent}(?![a-z])", text.lower()):
            return intent  # type: ignore[return-value]
    return None


def _classify_intent_by_llm(text: str) -> Intent | None:
    """使用规范提示词调用模型做意图分类。"""
    settings = get_settings()
    if not settings.has_openai_key:
        return None

    user_block = (
        "## 待分类的用户消息\n"
        f"{text.strip()}\n\n"
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
        logger.exception("supervisor LLM 调用失败，将尝试离线降级")
        return None


def classify_intent(text: str, *, force_rules: bool = False) -> Intent:
    """默认：有 Key 时必须走模型；仅 force_rules / 无 Key / 调用失败时用规则降级。"""
    if force_rules:
        return classify_intent_by_rules(text)

    settings = get_settings()
    if settings.has_openai_key:
        llm_intent = _classify_intent_by_llm(text)
        if llm_intent is not None:
            return llm_intent
        if settings.allow_offline_fallback:
            logger.warning("模型路由失败，降级为关键词规则")
            return classify_intent_by_rules(text)
        logger.error("模型路由失败且未允许离线降级，回退 chitchat")
        return "chitchat"

    if settings.allow_offline_fallback:
        return classify_intent_by_rules(text)
    return "chitchat"


def supervisor_node(state: SupportState) -> dict:
    text = last_user_text(state)
    intent = classify_intent(text, force_rules=False)
    return {"intent": intent}
