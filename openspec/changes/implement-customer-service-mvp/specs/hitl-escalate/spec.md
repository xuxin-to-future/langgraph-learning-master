## ADDED Requirements

### Requirement: 转人工使用 LangGraph interrupt
`escalate` 节点 SHALL 将 `needs_human` 设为 true，并使用 LangGraph `interrupt`（或等价暂停），使运行等待人工输入后再继续。

#### Scenario: 用户要求人工
- **WHEN** 用户表示要投诉并找人工
- **THEN** `intent` 为 `escalate`，响应中 `needs_human=true`，图暂停等待 resume

### Requirement: 会话 checkpoint 支持恢复
系统 SHALL 使用 checkpointer 编译图。开发 MAY 使用 `MemorySaver`；需持久演示时 MAY 使用 `SqliteSaver`。恢复时 SHALL 使用与原 `sessionId` 相同的 `thread_id`。

#### Scenario: 同一会话多轮
- **WHEN** 两轮对话使用相同 `sessionId`
- **THEN** 该 thread 的消息历史通过 checkpoint 保留

### Requirement: 管理端 resume 继续图执行
`POST /v1/admin/escalate/{sessionId}/resume` SHALL 恢复被中断的运行（例如通过 `Command(resume=...)`），并返回继续后的对话结果。

#### Scenario: 运营在 interrupt 后 resume
- **WHEN** 会话正在等待人工，运营提交 resume（含决定/留言）
- **THEN** 图继续执行，客户端收到更新后的回答，且不会新建无关 thread
