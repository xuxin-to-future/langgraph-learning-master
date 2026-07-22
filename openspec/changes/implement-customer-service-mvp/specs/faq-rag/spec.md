## ADDED Requirements

### Requirement: 知识库可检索
系统 SHALL 能从 `customer_service/knowledge/*.md` 检索与 FAQ 问题相关的片段。一期 SHALL 支持关键词（或等价确定性）检索；向量检索 MAY 在后续通过配置加入。

#### Scenario: 命中退款政策
- **WHEN** 用户询问「退款政策是什么？」
- **THEN** 检索结果包含 `support-policy.md`（或等价退款章节）的内容，且 `answer` 引用或体现该政策

### Requirement: FAQ 节点产出回答与依据
`faq` 节点 SHALL 设置 `retrieved_docs` 与 `answer`。当无相关内容时，系统 SHALL 以 HTTP 200 返回明确的未找到类回答，并 MAY 建议建工单或转人工。

#### Scenario: 知识库未命中
- **WHEN** 查询未匹配任何知识片段
- **THEN** `answer` 说明未找到，且不编造政策细节

### Requirement: 离线 FAQ 路径
在无 LLM 时，FAQ 回答 SHALL 仍能基于检索片段返回可用的模板/摘要。

#### Scenario: 离线 FAQ 回答
- **WHEN** 启用离线降级且检索成功
- **THEN** `answer` 非空，且内容基于 `retrieved_docs`
