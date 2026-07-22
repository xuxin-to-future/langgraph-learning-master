## ADDED Requirements

### Requirement: 管理页可上传文档到知识库
系统 SHALL 提供 Web 管理页面，使用户无需手工调 API 即可：选择或创建知识库、上传 `.md`/`.txt`、看到文档列表与处理状态。

#### Scenario: 页面上传后列表可见
- **WHEN** 用户在管理页选择知识库并上传合法文本文件
- **THEN** 页面展示该文档条目，且状态最终为就绪（ready）或明确失败原因

#### Scenario: 管理页可打开
- **WHEN** 用户访问 RAG 服务根路径或 `/admin`
- **THEN** 返回可交互的上传管理界面（非目录列表）

### Requirement: 管理页调用本服务 API
管理页 SHALL 通过本服务的 HTTP API 完成上传与列表，SHALL NOT 绕过服务直接写库。

#### Scenario: 上传走统一入库接口
- **WHEN** 用户在页面点击上传
- **THEN** 服务端走与 `POST` 文档上传相同的入库流水线
