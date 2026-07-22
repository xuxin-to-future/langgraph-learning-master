## ADDED Requirements

### Requirement: 文档可删除并清理索引
系统 SHALL 支持删除文档，并移除其文件与 chunk/索引，使后续 retrieve 不再命中已删内容。

#### Scenario: 删除后不可召回
- **WHEN** 删除某已入库文档后再用原能命中的 query 检索
- **THEN** 结果中不再出现该 doc_id 的 chunk

### Requirement: 支持重索引
系统 SHALL 提供对已有文档的 reindex，使其 chunk 与索引与当前文件内容一致。

#### Scenario: 更新后重索引生效
- **WHEN** 文档内容变更并触发 reindex 成功
- **THEN** retrieve 可命中新内容相关片段

### Requirement: retrieve 支持过滤
retrieve SHALL 支持按 `kb_id`（必填或可默认）以及可选 `filters.doc_ids` 限制召回范围。

#### Scenario: 按 doc_ids 过滤
- **WHEN** filters.doc_ids 仅包含文档 A
- **THEN** 返回 chunks 的 doc_id 均属于 A
