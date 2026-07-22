## ADDED Requirements

### Requirement: 对话接口将 sessionId 映射为 thread_id
`POST /v1/chat` SHALL 接受 `sessionId`（JSON）/ `session_id`（Python 别名）；缺少 `sessionId` 或消息为空时返回 400；并以 `configurable.thread_id = session_id` 调用图。

#### Scenario: 合法对话请求
- **WHEN** 客户端提交 `{ "sessionId": "user-42", "message": "退款政策是什么？" }`
- **THEN** 响应为 200，包含 `sessionId`、`intent`、`answer` 及 ChatResponse 相关字段

#### Scenario: 缺少 sessionId
- **WHEN** 客户端省略 `sessionId`
- **THEN** API 返回 400，且不调用图

### Requirement: 健康检查与工单/管理路由存在
应用 SHALL 暴露 `GET /health`、工单查询与 escalate resume（路径见设计）。API 模块 SHALL 只做校验与序列化；业务分支位于 graph/services。

#### Scenario: 健康检查正常
- **WHEN** 客户端调用 `GET /health`
- **THEN** 返回 200，表示服务可用

### Requirement: 错误映射
协议/基础设施失败 SHALL 使用 4xx/5xx。可预期业务结果（FAQ 未命中、等待人工）SHALL 使用 200，并用明确字段表达（如 `needs_human`、清晰的 `answer`）。SHALL NOT 向客户端返回堆栈。

#### Scenario: 等待人工仍为成功响应
- **WHEN** escalate 暂停等待人工
- **THEN** HTTP 状态为 200，且 `needs_human` 为 true

### Requirement: 流式接口不阻断 MVP
`POST /v1/chat/stream` MAY 延后实现；MVP 成功不以 SSE 为必要条件。若后续实现，MUST NOT 破坏同步 `/v1/chat`。

#### Scenario: 无流式接口时同步对话仍可用
- **WHEN** 仅实现了 `POST /v1/chat`，客户端发送合法 FAQ 问题
- **THEN** 同步接口返回 200 与合法 ChatResponse，且 MVP 验收不依赖 `/v1/chat/stream`
