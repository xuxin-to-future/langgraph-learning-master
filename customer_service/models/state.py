"""LangGraph 共享状态定义。

字段约定（节点只写职责内字段）：

| 字段 | 谁写入 | 默认/约定 |
|------|--------|-----------|
| messages | 入口输入 + 各节点追加 | 使用 `add_messages` reducer；首轮由 API 注入 HumanMessage |
| intent | supervisor | 路由前必须已设置；取值见 `Intent` |
| retrieved_docs | faq | 未走 FAQ 时可缺省；FAQ 无命中时为空列表 |
| ticket_id | ticket | 非工单路径为 None / 缺省 |
| needs_human | escalate | 默认视作 False；转人工时为 True |
| answer | faq / ticket / chitchat / escalate | 一轮成功结束后应非空 |
| error | 任意节点（可恢复错误） | 缺省或 None 表示无错误 |

`total=False`：允许部分更新；编译图时以节点返回的局部 dict 合并进状态。
"""

from __future__ import annotations

from typing import Annotated, Literal

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

Intent = Literal["faq", "ticket", "chitchat", "escalate"]


class SupportState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    intent: Intent
    retrieved_docs: list[str]
    ticket_id: str | None
    needs_human: bool
    answer: str
    error: str | None
