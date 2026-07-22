## 1. P0 基础：包骨架与配置

- [x] 1.1 新建 `rag_service/` 包结构：`api/` `models/` `services/` `storage/` `web/` `config/`
- [x] 1.2 实现 `settings`：数据目录、db 路径、上传大小/扩展名白名单、embedding 相关 env
- [x] 1.3 `create_app()` + `GET /health`；`requirements.txt` 按需补充依赖
- [x] 1.4 SQLite 元数据 schema：kb / documents / chunks（含状态字段）

## 2. P0 知识库 API（rag-kb）

- [x] 2.1 `POST /v1/kb` 创建知识库
- [x] 2.2 `GET /v1/kb` 列表；`GET /v1/kb/{kb_id}` 详情
- [x] 2.3 启动时确保存在 default 知识库（或首次访问自动创建）
- [x] 2.4 单测：创建后可列表查询

## 3. P0 入库流水线（rag-ingest）

- [x] 3.1 文件落盘到 `data/rag/files/{kb_id}/{doc_id}/`
- [x] 3.2 解析 `.md`/`.txt` 文本；非法扩展名 4xx
- [x] 3.3 切片器：按 `##` / 段落 + 最大长度，生成 chunks
- [x] 3.4 写入 chunks 表；文档状态 pending → ready / failed
- [x] 3.5 `POST /v1/kb/{kb_id}/documents` multipart 上传
- [x] 3.6 `GET /v1/documents/{doc_id}` 返回 status、chunk_count
- [x] 3.7 单测：上传含「退款」的 md → ready 且 chunk_count≥1

## 4. P0 索引与召回（rag-retrieve）

- [x] 4.1 关键词索引（FTS5 或等价）随入库更新
- [x] 4.2 `POST /v1/retrieve`：keyword 召回 + score + 溯源字段
- [x] 4.3 向量嵌入与存储（有 Key/模型时）；无则跳过但不破坏 keyword
- [x] 4.4 混合融合（RRF 或加权）；`methods` 可只选 keyword/vector
- [x] 4.5 单测：入库后退款 query 命中对应 source

## 5. P0 管理页上传落库（rag-admin-ui）【可用性门槛】

- [x] 5.1 静态页：知识库选择/创建、文件选择、上传按钮
- [x] 5.2 文档列表：title、status、chunk_count、时间；支持刷新
- [x] 5.3 上传成功/失败提示；failed 显示错误摘要
- [x] 5.4 FastAPI 挂载静态页（`/` 或 `/admin`）
- [x] 5.5 README：如何启动 8100 端口并用页面上传的步骤
- [x] 5.6 手工验收：浏览器上传 md → 列表 ready → retrieve 可查

## 6. P1 重排（rag-rerank）

- [x] 6.1 retrieve 支持 `rerank` 布尔参数与 recall_top_n
- [x] 6.2 接入可选 rerank 实现（无模型则降级并打日志）
- [x] 6.3 单测或手册：rerank=true 时返回条数 ≤ top_k

## 7. P1 文档生命周期与过滤（rag-lifecycle）

- [x] 7.1 `DELETE /v1/documents/{doc_id}` 删文件+chunks+索引
- [x] 7.2 `POST /v1/documents/{doc_id}/reindex` 重解析索引
- [x] 7.3 管理页：删除按钮；可选重新索引
- [x] 7.4 retrieve `filters.doc_ids` 过滤
- [x] 7.5 单测：删除后不再命中；过滤只返回指定 doc

## 8. P1 简单评测（rag-eval）

- [x] 8.1 增加黄金集文件（如退款问句 → 期望 source 关键词）
- [x] 8.2 评测脚本或 `POST /v1/eval/run` 输出通过/失败
- [x] 8.3 README 补充如何跑评测

## 9. 可选：客服对接预留（不阻塞 P0 页面）

- [x] 9.1 `customer_service` 增加 `RAG_PROVIDER`/`RAG_BASE_URL` 配置项
- [x] 9.2 实现 `rag_client.retrieve` HTTP 客户端
- [x] 9.3 faq 节点可切换 local/http（默认仍 local，直到验收通过）

## 10. 收尾

- [x] 10.1 `.gitignore` 忽略 `data/rag/**` 运行时文件（保留 gitkeep）
- [x] 10.2 根 README 或 `rag_service/README.md` 写清 P0/P1 范围与启动方式
- [x] 10.3 `openspec validate self-hosted-rag-mvp` 通过
