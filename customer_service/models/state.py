"""LangGraph 共享状态定义。

字段约定（节点只写职责内字段）：

| 字段 | 谁写入 | 默认/约定 |
|------|--------|-----------|
| messages | 入口输入 + 各叶子节点追加 AIMessage | `add_messages`；API 注入 HumanMessage |
| conversation_summary | session（超 token 预算时） | 旧轮次压缩摘要 |
| session_memory | session（每轮）+ 叶子回写 last_* | 工作记忆 / DST |
| turn_type | session | 本轮会话动作 |
| need_retrieve | session | 是否查知识库 |
| standalone_query | session | 改写后的独立检索问句 |
| intent | supervisor | 路由前必须已设置 |
| retrieved_docs | faq | 未走 FAQ 时可缺省 |
| ticket_id | ticket | 表单建单后由 API 返回 |
| needs_human | escalate | 默认 False |
| needs_ticket_form | ticket | 对话触发工单表单时为 True |
| answer | faq / ticket / chitchat / escalate | 一轮成功结束后应非空 |
| error | 任意节点（可恢复错误） | 缺省或 None 表示无错误 |

`total=False`：允许部分更新；编译图时以节点返回的局部 dict 合并进状态。
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

Intent = Literal["faq", "ticket", "chitchat", "escalate"]

TurnType = Literal[
    "new_question",
    "followup",
    "session_recall",
    "topic_switch",
    "clarify",
    "other",
    "slot_fill",  # 预留 B，本轮不主动产出
]


class SessionMemory(TypedDict, total=False):
    topic: str
    entities: list[str]
    last_user_question: str
    last_assistant_answer: str
    slots: dict[str, Any]


class SupportState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    conversation_summary: str
    session_memory: SessionMemory
    turn_type: TurnType
    need_retrieve: bool
    standalone_query: str
    intent: Intent
    retrieved_docs: list[str]
    ticket_id: str | None
    needs_human: bool
    needs_ticket_form: bool
    answer: str
    error: str | None
