## ADDED Requirements

### Requirement: 可选通用 rerank
当 retrieve 请求 `rerank=true` 且配置可用时，系统 SHALL 对初召结果重排后再截断为 top_k；不可用时 SHALL 降级为未重排结果或返回明确错误（实现选定一种并文档化）。

#### Scenario: 开启 rerank 仍返回 top_k
- **WHEN** 客户端 retrieve 且 rerank=true、初召有多条命中
- **THEN** 返回条数不超过 top_k，且顺序可为重排后顺序
