## ADDED Requirements

### Requirement: 创建工单并持久化到 SQLite
系统 SHALL 在本地 SQLite（默认路径 `data/tickets.db`）创建支持工单，并返回稳定的 `ticket_id`。写库失败时 MUST NOT 伪造 `ticket_id`。

#### Scenario: 创建无法登录工单
- **WHEN** 用户请求为「无法登录」创建工单
- **THEN** `intent` 为 `ticket`，库中写入一行，且响应包含非空 `ticket_id`

### Requirement: 按 id 查询工单
系统 SHALL 支持按 `ticket_id` 查询工单，返回核心字段（id、主题/摘要、状态、创建时间等适用字段）。

#### Scenario: 查询已存在工单
- **WHEN** 客户端请求已知 id 的 `GET /v1/tickets/{ticket_id}`
- **THEN** API 返回 200 及该工单数据

#### Scenario: 工单不存在
- **WHEN** ticket id 不存在
- **THEN** API 返回 404

### Requirement: Ticket 节点走服务层
`ticket` 节点 SHALL 调用 `services.tickets`（必要时经 tools），并在 state 上设置 `ticket_id` 与 `answer`；SHALL NOT 在 API 层直接写裸 SQL。

#### Scenario: 分层保持
- **WHEN** 通过对话创建工单
- **THEN** 持久化逻辑位于 `services/tickets.py`（或其模块辅助函数），而非 `api/routes_*.py`
