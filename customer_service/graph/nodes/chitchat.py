"""寒暄 / 会话回忆节点。"""

from __future__ import annotations

from langchain_core.messages import AIMessage

from customer_service.config.settings import get_settings
from customer_service.graph.nodes._message_utils import (
    last_user_text,
    session_context_from_state,
)
from customer_service.models.state import SupportState
from customer_service.services.session_memory import (
    normalize_session_memory,
    touch_last_turns,
)


def chitchat_node(state: SupportState) -> dict:
    text = last_user_text(state)
    ctx = session_context_from_state(state)
    memory = normalize_session_memory(state.get("session_memory"))
    turn_type = str(state.get("turn_type") or "")

    if turn_type == "session_recall":
        answer = _recall_answer(memory, ctx.prompt_block)
    else:
        answer = _answer(text, ctx.prompt_block)

    new_memory = touch_last_turns(memory, text, answer)
    return {
        "answer": answer,
        "error": None,
        "needs_ticket_form": False,
        "needs_human": False,
        "retrieved_docs": [],
        "session_memory": new_memory,
        "messages": [AIMessage(content=answer)],
    }


def _recall_answer(memory: dict, prompt_block: str) -> str:
    last_q = (memory.get("last_user_question") or "").strip()
    if last_q:
        return f"您上一轮问的是：「{last_q}」。"
    # 从 prompt_block 里找最近一条不同于回忆句的用户话
    for line in reversed((prompt_block or "").splitlines()):
        line = line.strip()
        if line.startswith("用户："):
            cand = line[len("用户：") :].strip()
            if cand and "刚才" not in cand:
                return f"您上一轮问的是：「{cand}」。"
    return "当前会话里我还没有记录到您更早的提问。您可以直接再说一遍问题。"


def _answer(text: str, session_block: str) -> str:
    settings = get_settings()
    lower = text.lower()
    has_history = "助手：" in (session_block or "") or "会话摘要" in (session_block or "")
    if settings.has_openai_key and has_history:
        llm = _chitchat_with_llm(text, session_block)
        if llm:
            return llm

    if any(k in text for k in ("你好", "您好", "嗨", "hello", "hi")) or "hello" in lower:
        return "您好！我是智服助手，可以帮您查询政策、创建工单，或在需要时转接人工。"
    if any(k in text for k in ("谢谢", "感谢", "拜拜", "再见")):
        return "不客气，有需要随时找我。"
    return (
        "我更擅长解答产品/政策问题、帮您创建工单，或转接人工客服。"
        "您可以直接描述问题，例如「退款政策是什么？」"
    )


def _chitchat_with_llm(text: str, session_block: str) -> str | None:
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_openai import ChatOpenAI

        settings = get_settings()
        llm = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            temperature=0.4,
        )
        resp = llm.invoke(
            [
                SystemMessage(
                    content=(
                        "你是企业智能客服的寒暄助手。简短、礼貌地回应用户。"
                        "若用户询问刚才问了什么，根据会话上下文准确复述。"
                        "若用户在追问业务，引导其直接提问政策/功能问题。"
                        "不要编造业务事实。只输出对用户可见的回复。"
                    )
                ),
                HumanMessage(
                    content=(
                        f"{session_block}\n\n"
                        f"## 用户本轮\n{text}\n\n## 请回复"
                    )
                ),
            ]
        )
        out = str(getattr(resp, "content", "") or "").strip()
        return out or None
    except Exception:
        return None
