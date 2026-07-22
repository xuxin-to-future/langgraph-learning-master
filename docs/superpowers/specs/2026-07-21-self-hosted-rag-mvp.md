# 自研 RAG 最小能力清单 + API 草案

**目标：** 借鉴成熟 RAG 产品的能力边界，自研轻量检索中台；客服项目（LangGraph）只消费召回结果，不绑定 RAGFlow。  
**原则：** 先薄接口、可替换实现；一期够用即可，二期再加深解析与评测。

---

## 1. 与客服的边界

```text
┌─────────────────────────────┐     ┌──────────────────────────────┐
│  rag-service（自研）         │     │  customer_service（现有）      │
│  解析 · 索引 · 召回 · 可选重排 │ ──► │  意图 · 改写 · 业务过滤 · 生成 │
│  知识库 CRUD                 │     │  工单 · HITL · 会话           │
└─────────────────────────────┘     └──────────────────────────────┘
```

| 归属 RAG | 归属客服 |
|----------|----------|
| 文档入库、切片、向量/关键词索引 | Supervisor 意图路由 |
| `retrieve` 召回 | query 改写（可选）、业务加权 |
| 可选通用 rerank | 提示词生成、引用展示 |
| chunk 溯源（doc_id / chunk_id） | 工单 / 转人工 |

一期客服侧：把现有 `services/rag.py` 换成调用本 API；本地关键词实现可作为 `provider=local` 降级。

---

## 2. 最小能力清单（MVP）

### P0（必须有）

| 能力 | 说明 | 一期建议 |
|------|------|----------|
| 知识库 | 至少一个 dataset/kb | 单库 `default` 即可 |
| 文档入库 | 上传或登记文件，异步/同步解析 | 先支持 `.md` / `.txt` |
| 切片 | 按标题/段落切 chunk，保留来源 | 标题优先 + 长度上限 |
| 索引 | chunk 可被检索 | 关键词（必做）+ 向量（强烈建议） |
| 召回 | `query → top_k chunks` | 混合召回：向量 ∪ 关键词，简单融合 |
| 溯源 | 每条含 `doc_id`、`chunk_id`、`source`、`text`、`score` | 生成侧引用必备 |
| 健康检查 | 服务存活 | `/health` |

### P1（紧随其后）

| 能力 | 说明 |
|------|------|
| 通用 rerank | 召回 top_n 后再压到 top_k（可配置开关） |
| 文档更新/删除 | 改文档后重建该 doc 的 chunk 索引 |
| 按 doc/kb 过滤 | retrieve 时 `doc_ids` / `kb_id` |
| 简单评测集 | 黄金问句 → 期望命中 doc/chunk |

### P2（明确不做，避免一期膨胀）

- 多租户控制台、Agent 画布、复杂权限体系  
- 全格式 OCR / 表格深度解析（等业务真需要再加）  
- 图谱检索、多模态以图搜图  
- 与客服会话状态耦合（RAG 保持无状态检索服务）

---

## 3. 核心数据模型（逻辑）

```text
KnowledgeBase
  id, name, embedding_model?, created_at

Document
  id, kb_id, title, source(uri|path), status(pending|ready|failed), created_at

Chunk
  id, doc_id, kb_id, text, metadata(heading, page?), embedding?, created_at
```

检索命中：

```text
RetrievedChunk
  chunk_id, doc_id, kb_id, text, source, score, score_detail?
```

---

## 4. API 草案（HTTP JSON）

Base：`http://rag-service:8100`（示例）  
鉴权一期可用：`Authorization: Bearer <RAG_API_KEY>`（可选）

### 4.1 健康检查

`GET /health`

```json
{ "status": "ok", "version": "0.1.0" }
```

### 4.2 知识库

`POST /v1/kb`

```json
{ "name": "customer-support", "description": "客服政策与产品" }
```

`GET /v1/kb` → 列表  
`GET /v1/kb/{kb_id}` → 详情

### 4.3 文档

`POST /v1/kb/{kb_id}/documents`  
- `multipart/form-data`：`file` + 可选 `title`  
或 JSON 登记本地路径（仅内网演示）：

```json
{ "title": "退款政策", "path": "/data/knowledge/support-policy.md" }
```

响应：

```json
{
  "doc_id": "doc_xxx",
  "status": "pending"
}
```

`GET /v1/documents/{doc_id}` → 含 `status`、`chunk_count`  
`DELETE /v1/documents/{doc_id}` → 删文档及索引  

`POST /v1/documents/{doc_id}/reindex` → 强制重解析索引

### 4.4 召回（客服主依赖）

`POST /v1/retrieve`

```json
{
  "kb_id": "kb_default",
  "query": "退款政策是什么？",
  "top_k": 5,
  "recall_top_n": 20,
  "methods": ["vector", "keyword"],
  "rerank": false,
  "filters": {
    "doc_ids": null
  }
}
```

响应：

```json
{
  "query": "退款政策是什么？",
  "chunks": [
    {
      "chunk_id": "chk_1",
      "doc_id": "doc_policy",
      "kb_id": "kb_default",
      "source": "support-policy.md",
      "text": "订阅类服务在购买后 7 天内……",
      "score": 0.87,
      "score_detail": {
        "vector": 0.82,
        "keyword": 0.91,
        "rerank": null
      }
    }
  ]
}
```

约定：

- `recall_top_n`：初召数量；`top_k`：最终返回  
- `rerank=true` 时用通用模型重排（P1）  
- `score` 统一为融合后分数，便于客服侧排序展示  

### 4.5（可选）仅关键词 / 仅向量调试

`POST /v1/retrieve` 已通过 `methods` 覆盖；不必再拆多个端点。

---

## 5. 客服对接方式（替换点）

当前：`customer_service/services/rag.py` 本地读 `knowledge/*.md`。  

目标适配层：

```text
faq_node
  → rag_client.retrieve(query, kb_id, top_k)
  → answer_with_llm(query, chunks)
```

环境变量草案：

```env
RAG_PROVIDER=local|http
RAG_BASE_URL=http://127.0.0.1:8100
RAG_API_KEY=
RAG_KB_ID=kb_default
RAG_TOP_K=5
RAG_RERANK=false
```

`RAG_PROVIDER=local`：保留现有关键词实现，便于无 RAG 服务时演示。

---

## 6. 召回策略（一期默认）

1. **Query**：客服可先做轻量改写（可选，二期）  
2. **并行召回**：向量 top_n + 关键词 top_n  
3. **融合**：RRF 或加权分（实现任选一种，API 对外只暴露 `score`）  
4. **截断**：取 top_k  
5. **可选 rerank**：对 top_n 重排后再截断  

客服侧二期再加：按 `intent=faq` 限制某 kb、提升政策类 `doc_id` 权重等。

---

## 7. 分期落地顺序

| 阶段 | 交付 |
|------|------|
| M0 | 定 API + `RetrievedChunk` 契约；客服加 `http` client 空壳，local 仍可用 |
| M1 | md/txt 入库 + 切片 + 关键词召回 API |
| M2 | 向量索引 + 混合召回 |
| M3 | rerank 开关 + 文档更新删除 |
| M4 | 黄金集评测脚本；客服默认切 `RAG_PROVIDER=http` |

---

## 8. 非功能（最小）

- 延迟：单次 retrieve P95 &lt; 500ms（不含 rerank；含 rerank 另定）  
- 日志：`request_id`、kb_id、query 哈希、命中数  
- 失败：RAG 不可用时客服可降级 local 或返回「知识库暂不可用」  

---

## 9. 明确不从 RAGFlow 照搬的部分

- 重型前端与多租户运营台  
- 与对话 Agent 强绑定的「一站式 Chat」  
- 过早支持全文件格式与复杂版面  

只借鉴：**切片质量、混合召回、溯源字段、召回→重排流水线**。

---

## 10. 验收标准（对接客服后）

1. 「退款政策是什么？」retrieve 命中政策类 chunk，且含 `source`  
2. 客服 FAQ 回答带来源，且主要依据召回文本  
3. 关掉向量仅关键词、或关掉关键词仅向量，接口仍可用（便于排障）  
4. `RAG_PROVIDER=local` 与 `http` 切换无需改图节点代码（只改配置/客户端）
