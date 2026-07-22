## 为什么（Why）

客服 FAQ 目前依赖本地 `knowledge/*.md` 关键词检索，无法通过页面持续扩充知识。需要自研轻量 RAG 中台（借鉴成熟产品能力、不绑定 RAGFlow），先交付 **P0/P1**：文档可上传入库、可切片索引、可召回，并提供 **管理页上传落成知识库**；再为客服 `retrieve` 对接预留接口。

## 变更内容（What Changes）

- 新增独立包 `rag_service/`（FastAPI）：知识库、文档上传、解析切片、索引、召回 API
- P0：关键词索引必做；向量索引在同变更内紧随实现（混合召回）
- P0：Web 管理页——选择知识库、上传 `.md`/`.txt`、查看文档状态与列表
- P1：可选 rerank、文档更新/删除与重索引、retrieve 过滤、简单黄金集评测
- 客服侧：增加 `RAG_PROVIDER` 适配层任务（可后置），不阻塞 RAG 入库页交付

**非目标：** RAGFlow 级运营台、多租户、全格式 OCR、图谱/多模态、与客服会话状态耦合。

## 能力（Capabilities）

### 新增能力

- `rag-kb`：知识库创建与查询
- `rag-ingest`：文档上传、解析切片、索引构建与状态机
- `rag-retrieve`：混合召回与溯源字段
- `rag-admin-ui`：知识库上传与文档管理页面
- `rag-rerank`：通用重排开关（P1）
- `rag-lifecycle`：文档更新/删除/重索引与过滤（P1）
- `rag-eval`：简单评测集（P1）

### 修改中的能力

- （无）主库 `openspec/specs/` 尚无既有 RAG capability

## 影响范围（Impact）

- **新增代码：** `rag_service/**`、`tests/rag_service/**`、可选静态页挂载
- **依赖：** FastAPI、SQLite、可选 embedding/rerank 相关库
- **数据：** `data/rag/`（文件 + sqlite，gitignore）
- **文档：** `docs/superpowers/specs/2026-07-21-self-hosted-rag-mvp.md`
- **客服：** 后期对接；本期可不改图逻辑
