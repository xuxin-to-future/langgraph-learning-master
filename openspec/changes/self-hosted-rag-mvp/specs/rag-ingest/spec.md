## ADDED Requirements

### Requirement: 支持上传 md/txt 并解析入库
系统 SHALL 接受 `.md` / `.txt` 上传（或等价登记），创建 Document，解析文本后按标题/段落切片写入 Chunk，并建立可检索索引。

#### Scenario: 上传后退款政策类文档就绪
- **WHEN** 用户向某 kb 上传包含退款政策内容的 markdown 文件
- **THEN** 文档 `status` 变为 `ready`，且 `chunk_count` ≥ 1

#### Scenario: 不支持的类型被拒绝
- **WHEN** 用户上传不支持的扩展名（如 `.exe`）
- **THEN** API 返回 4xx 且不创建 ready 文档

### Requirement: 文档状态可查询
系统 SHALL 通过 `GET /v1/documents/{doc_id}` 返回 status、title、kb_id、chunk_count；失败时 SHALL 提供可读错误信息。

#### Scenario: 查询已就绪文档
- **WHEN** 文档处理成功后查询该 doc_id
- **THEN** status 为 `ready` 且 chunk_count > 0
