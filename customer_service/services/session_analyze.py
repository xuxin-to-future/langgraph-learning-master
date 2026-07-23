"""会话轮次结构化分析：turn_type / need_retrieve / standalone_query / memory。"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from customer_service.config.settings import get_settings
from customer_service.models.state import SessionMemory, TurnType
from customer_service.services.session_memory import (
    heuristic_session_update,
    merge_memory,
    normalize_session_memory,
    normalize_turn_type,
)

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "session.md"


@dataclass(frozen=True)
class SessionAnalyzeResult:
    turn_type: TurnType
    need_retrieve: bool
    standalone_query: str
    session_memory: SessionMemory


@lru_cache(maxsize=1)
def load_session_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _extract_json_object(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def parse_analyze_payload(
    data: dict[str, Any],
    *,
    user_text: str,
    memory: SessionMemory,
    has_history: bool,
) -> SessionAnalyzeResult:
    turn = normalize_turn_type(str(data.get("turn_type") or ""), has_history=has_history)
    if "need_retrieve" in data:
        need = bool(data.get("need_retrieve"))
    else:
        need = turn in {"new_question", "followup", "topic_switch"}
    if turn == "session_recall":
        need = False

    standalone = str(data.get("standalone_query") or "").strip() or (user_text or "").strip()
    mem_patch = data.get("memory") if isinstance(data.get("memory"), dict) else {}
    # 忽略模型对 last_* / slots 的乱写
    safe_patch = {
        k: mem_patch[k]
        for k in ("topic", "entities")
        if k in mem_patch
    }
    new_mem = merge_memory(memory, safe_patch)
    return SessionAnalyzeResult(
        turn_type=turn,
        need_retrieve=need,
        standalone_query=standalone,
        session_memory=new_mem,
    )


def analyze_turn(
    user_text: str,
    *,
    prompt_block: str = "",
    memory: SessionMemory | dict[str, Any] | None = None,
    has_history: bool = False,
) -> SessionAnalyzeResult:
    """生产路径：LLM 结构化分析；失败回退启发式。"""
    q = (user_text or "").strip()
    mem = normalize_session_memory(memory)
    if not q:
        return SessionAnalyzeResult(
            turn_type="other",
            need_retrieve=False,
            standalone_query="",
            session_memory=mem,
        )

    settings = get_settings()
    if not settings.has_openai_key:
        fb = heuristic_session_update(q, mem, has_history=has_history)
        return SessionAnalyzeResult(
            turn_type=fb["turn_type"],
            need_retrieve=fb["need_retrieve"],
            standalone_query=fb["standalone_query"],
            session_memory=fb["session_memory"],
        )

    history = ""
    if (prompt_block or "").strip():
        history = f"## 会话上下文\n{prompt_block.strip()}\n\n"
    mem_json = json.dumps(
        {
            "topic": mem.get("topic") or "",
            "entities": mem.get("entities") or [],
            "last_user_question": mem.get("last_user_question") or "",
        },
        ensure_ascii=False,
    )

    user_block = (
        f"{history}"
        f"## 当前工作记忆\n{mem_json}\n\n"
        f"## 用户本轮\n{q}\n\n"
        "## 请输出 JSON"
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
                SystemMessage(content=load_session_prompt()),
                HumanMessage(content=user_block),
            ]
        )
        raw = str(getattr(resp, "content", "") or "")
        data = _extract_json_object(raw)
        if data is None:
            logger.warning("session analyze JSON parse failed: %r", raw[:200])
            raise ValueError("unparseable session analyze output")
        return parse_analyze_payload(
            data, user_text=q, memory=mem, has_history=has_history
        )
    except Exception:
        logger.exception("session analyze failed; using heuristic")
        fb = heuristic_session_update(q, mem, has_history=has_history)
        return SessionAnalyzeResult(
            turn_type=fb["turn_type"],
            need_retrieve=fb["need_retrieve"],
            standalone_query=fb["standalone_query"],
            session_memory=fb["session_memory"],
        )
