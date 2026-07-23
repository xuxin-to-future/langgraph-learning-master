"""会话工作记忆（Dialogue State）辅助：规范化、启发式降级、回写 last_*。"""

from __future__ import annotations

import re
from typing import Any

from customer_service.models.state import SessionMemory, TurnType

_VALID_TURN: set[str] = {
    "new_question",
    "followup",
    "session_recall",
    "topic_switch",
    "clarify",
    "other",
    "slot_fill",
}

_RECALL_RE = re.compile(
    r"(刚才|上一[轮句个]?|之前).{0,12}(问|说|讲)|我(刚刚|刚才)?(问|说)的是什么|"
    r"你(刚刚|刚才)?(说|答|回)了什么|我问过什么",
    re.I,
)

_FOLLOWUP_RE = re.compile(
    r"整理|公式|归纳|总结|详细|再说|上面|那个|这个|换个|写成|继续|补充|还有呢|然后呢",
)

_ASSISTANT_ANSWER_MAX = 1200


def empty_session_memory() -> SessionMemory:
    return {
        "topic": "",
        "entities": [],
        "last_user_question": "",
        "last_assistant_answer": "",
        "slots": {},
    }


def normalize_session_memory(raw: Any) -> SessionMemory:
    base = empty_session_memory()
    if not isinstance(raw, dict):
        return base
    topic = str(raw.get("topic") or "").strip()
    entities_raw = raw.get("entities") or []
    entities: list[str] = []
    if isinstance(entities_raw, list):
        for item in entities_raw:
            s = str(item or "").strip()
            if s and s not in entities:
                entities.append(s)
    slots = raw.get("slots")
    if not isinstance(slots, dict):
        slots = {}
    return {
        "topic": topic,
        "entities": entities[:20],
        "last_user_question": str(raw.get("last_user_question") or "").strip(),
        "last_assistant_answer": str(raw.get("last_assistant_answer") or "").strip(),
        "slots": slots,
    }


def merge_memory(base: SessionMemory, patch: dict[str, Any] | None) -> SessionMemory:
    out = normalize_session_memory(base)
    if not patch:
        return out
    if "topic" in patch and patch["topic"] is not None:
        out["topic"] = str(patch["topic"] or "").strip()
    if "entities" in patch and patch["entities"] is not None:
        ents = patch["entities"]
        if isinstance(ents, list):
            cleaned: list[str] = []
            for item in ents:
                s = str(item or "").strip()
                if s and s not in cleaned:
                    cleaned.append(s)
            out["entities"] = cleaned[:20]
    if "last_user_question" in patch and patch["last_user_question"] is not None:
        out["last_user_question"] = str(patch["last_user_question"] or "").strip()
    if "last_assistant_answer" in patch and patch["last_assistant_answer"] is not None:
        ans = str(patch["last_assistant_answer"] or "").strip()
        if len(ans) > _ASSISTANT_ANSWER_MAX:
            ans = ans[:_ASSISTANT_ANSWER_MAX]
        out["last_assistant_answer"] = ans
    # slots 本轮不业务写入；若 patch 带来则规范化为空 dict 以外保留结构
    if "slots" in patch and isinstance(patch["slots"], dict):
        out["slots"] = patch["slots"]
    return out


def touch_last_turns(
    memory: SessionMemory | dict[str, Any] | None,
    user_text: str,
    assistant_text: str,
) -> SessionMemory:
    m = normalize_session_memory(memory)
    m["last_user_question"] = (user_text or "").strip()
    ans = (assistant_text or "").strip()
    if len(ans) > _ASSISTANT_ANSWER_MAX:
        ans = ans[:_ASSISTANT_ANSWER_MAX]
    m["last_assistant_answer"] = ans
    return m


def is_recall_utterance(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return bool(_RECALL_RE.search(t))


def is_followup_utterance(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if len(t) <= 20 and _FOLLOWUP_RE.search(t):
        return True
    return bool(_FOLLOWUP_RE.search(t)) and len(t) < 40


def normalize_turn_type(raw: str | None, *, has_history: bool) -> TurnType:
    val = (raw or "").strip().lower()
    if val == "slot_fill":
        # 本轮不启用 B：降为 followup / other
        return "followup" if has_history else "other"
    if val in _VALID_TURN:
        return val  # type: ignore[return-value]
    return "followup" if has_history else "new_question"


def heuristic_session_update(
    user_text: str,
    memory: SessionMemory | dict[str, Any] | None,
    *,
    has_history: bool,
) -> dict[str, Any]:
    """LLM 失败时的降级：推断 turn_type / need_retrieve / standalone_query / memory。"""
    q = (user_text or "").strip()
    mem = normalize_session_memory(memory)

    if is_recall_utterance(q):
        return {
            "turn_type": "session_recall",
            "need_retrieve": False,
            "standalone_query": q,
            "session_memory": mem,
        }

    if not has_history:
        topic = q[:40]
        return {
            "turn_type": "new_question",
            "need_retrieve": True,
            "standalone_query": q,
            "session_memory": merge_memory(mem, {"topic": topic}),
        }

    if is_followup_utterance(q):
        anchor = mem.get("last_user_question") or mem.get("topic") or ""
        standalone = f"{anchor} {q}".strip() if anchor else q
        return {
            "turn_type": "followup",
            "need_retrieve": True,
            "standalone_query": standalone,
            "session_memory": mem,
        }

    # 默认：有历史仍当可能追问，检索用原句；若很短且无业务词则 other
    if len(q) <= 6 and not any(c.isalnum() for c in q):
        return {
            "turn_type": "other",
            "need_retrieve": False,
            "standalone_query": q,
            "session_memory": mem,
        }

    return {
        "turn_type": "new_question",
        "need_retrieve": True,
        "standalone_query": q,
        "session_memory": merge_memory(mem, {"topic": q[:40]}),
    }
