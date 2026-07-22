## ADDED Requirements

### Requirement: retrieve 返回带来源的 chunks
`POST /v1/retrieve` SHALL 根据 query 与 kb_id 返回 top_k 条命中，每条包含 chunk_id、doc_id、kb_id、source、text、score。

#### Scenario: 退款问题命中已入库政策
- **WHEN** kb 中已有退款政策文档且客户端以「退款政策是什么？」调用 retrieve
- **THEN** 返回的 chunks 非空，且至少一条 text 或 source 与该政策文档相关

### Requirement: 支持关键词与向量方法开关
retrieve SHALL 支持 `methods` 含 `keyword` 与/或 `vector`；在仅有关键词索引时，仅 keyword 仍 SHALL 可用。

#### Scenario: 仅关键词可召回
- **WHEN** methods 仅为 `["keyword"]` 且文档已建关键词索引
- **THEN** 相关 query 仍能返回命中

### Requirement: 健康检查
系统 SHALL 提供 `GET /health` 返回可用状态。

#### Scenario: 探活成功
- **WHEN** 调用 `GET /health`
- **THEN** HTTP 200 且标识服务正常
