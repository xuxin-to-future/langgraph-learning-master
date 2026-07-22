## ADDED Requirements

### Requirement: SupportState 作为唯一共享图状态
系统 SHALL 使用与 LangGraph 兼容的 `SupportState`，至少包含 `messages`（配合 `add_messages` reducer）、`intent`、`retrieved_docs`、`ticket_id`、`needs_human`、`answer`、`error`。节点 SHALL 只写入自身职责内的字段。

#### Scenario: 一轮对话结束后状态字段齐全
- **WHEN** 一轮对话成功完成
- **THEN** 图状态包含非空 `answer`，且 `intent` 属于 `{faq, ticket, chitchat, escalate}`

### Requirement: Supervisor 先于技能节点路由
编译后的图 SHALL 从 `supervisor` 节点开始（由其设置 `intent`），再通过条件边（`route_by_intent`）分发到且仅分发到 `faq`、`ticket`、`chitchat`、`escalate` 之一。

#### Scenario: FAQ 意图分发
- **WHEN** supervisor 将 `intent` 设为 `faq`
- **THEN** 下一个执行的节点是 `faq`

#### Scenario: 转人工意图分发
- **WHEN** supervisor 将 `intent` 设为 `escalate`
- **THEN** 下一个执行的节点是 `escalate`

### Requirement: 离线规则版 Supervisor
当未配置 LLM API Key（或启用离线降级）时，supervisor SHALL 用确定性规则/关键词做意图分类，使三验收路径在无外部模型时仍可运行。

#### Scenario: 离线询问退款政策
- **WHEN** 用户在无 API Key 时询问退款政策
- **THEN** `intent` 为 `faq`，且图不会因缺少 LLM 而抛错中断

### Requirement: 通过 build_graph 编译图
`customer_service.graph.builder.build_graph` SHALL 返回已编译的 LangGraph 应用，支持 `invoke` / `ainvoke` / stream，并接受 `configurable.thread_id`。

#### Scenario: 带 thread_id 调用
- **WHEN** API 以 `config={"configurable": {"thread_id": "<sessionId>"}}` 调用图
- **THEN** 本次运行的状态与该 thread 关联，以便 checkpoint
