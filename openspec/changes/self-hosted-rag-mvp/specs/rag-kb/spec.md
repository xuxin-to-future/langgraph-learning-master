## ADDED Requirements

### Requirement: 可创建与查询知识库
系统 SHALL 支持创建知识库并列出/查询详情，至少存在一个可用 kb（可自动创建 default）。

#### Scenario: 创建知识库
- **WHEN** 客户端 `POST /v1/kb` 并提供名称
- **THEN** 返回新 `kb_id` 且后续列表可见

#### Scenario: 列出知识库
- **WHEN** 客户端 `GET /v1/kb`
- **THEN** 返回至少一个知识库条目（含 id 与 name）
