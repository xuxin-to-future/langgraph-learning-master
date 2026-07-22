# 自研 RAG 中台

知识库检索与管理（P0/P1）。**推荐**与客服同进程启动（见根目录 README）；亦可独立 8100 调试。

## 启动

### 统一入口（推荐 · 端口 8000）

```powershell
cd d:\langgraph-learning-master
uvicorn app.main:create_app --factory --reload --port 8000
```

- 管理页：http://127.0.0.1:8000/kb/
- 客服页：http://127.0.0.1:8000/
- API：同域 `/v1/kb` · `/v1/documents` · `/v1/retrieve`

### 独立调试（端口 8100）

```powershell
uvicorn rag_service.api.app:create_app --factory --reload --port 8100
```

- 探活：http://127.0.0.1:8100/health
- 管理页：http://127.0.0.1:8100/

## 用页面上传

1. 启动统一服务（**8000**）或独立 RAG（**8100**）。
2. 打开 http://127.0.0.1:8000/kb/ （或独立时的 `/`）。
3. 选择或创建知识库 → 上传 `.md` / `.txt` → 列表中状态为 `ready`。
4. 若升级过切片策略，对旧文档点「重索引」使新切分生效。

## 切片策略

对齐 RAGFlow **naive** 主路径（非 TitleChunker）：

1. 识别 Markdown `#`～`######`；短标题（&lt;50 token）并入下一段正文  
2. 按空行拆段后，用 **tiktoken `cl100k_base`** 打包  
3. 默认目标约 **512 token**，块间 **10%** 字符后缀 overlap  

| 环境变量 | 默认 | 说明 |
|----------|------|------|
| `RAG_CHUNK_TOKEN_NUM` | `512` | 块 token 预算 |
| `RAG_CHUNK_OVERLAP_PERCENT` | `10` | 0–90 |
| `RAG_CHUNK_MAX_CHARS` | `8000` | 超长段硬切兜底（已非主计量） |

## 客服对接

统一服务下建议：

```env
RAG_PROVIDER=http
RAG_BASE_URL=http://127.0.0.1:8000
RAG_KB_ID=kb_default
RAG_TOP_K=5
RAG_RERANK=true
```

独立双端口时把 `RAG_BASE_URL` 改为 `http://127.0.0.1:8100`。FAQ 节点走 `POST /v1/retrieve`，回答仍由客服侧 LLM 生成。

## 召回示例（Task 4）

```powershell
curl -X POST http://127.0.0.1:8000/v1/retrieve `
  -H "Content-Type: application/json" `
  -d "{\"kb_id\":\"kb_default\",\"query\":\"退款政策是什么？\",\"top_k\":5,\"methods\":[\"keyword\",\"vector\"]}"
```

- `methods` 可只传 `["keyword"]` 或 `["vector"]`。
- `recall_top_n`：初召条数；`top_k`：最终返回条数。
- `rerank=true`：对初召结果用 SiliconFlow `/rerank` 重排后再截断为 `top_k`。无 Key / 模型不可用时**降级**为未重排结果（打日志，不报错）。
- 无可用 embedding（无 Key / 模型不支持）时，向量自动跳过，关键词仍可用。
- 混合时用 **加权融合**（对齐 RAGFlow）：`score = w·vector + (1-w)·keyword`，默认 `w=0.7`（`RAG_VECTOR_SIMILARITY_WEIGHT` 或请求体 `vector_similarity_weight`）。
- `score_detail.keyword` 为词项覆盖率 ∈ [0,1]（不再用易顶满的 overlap/8）。
- `score_detail.vector` 为余弦相似度。

Embedding / Rerank 配置（可选，读根目录 `.env`）：

- 聊天：`OPENAI_API_KEY` / `OPENAI_BASE_URL`（如 DeepSeek）
- **向量（可分离）**：`RAG_EMBEDDING_API_KEY` / `RAG_EMBEDDING_BASE_URL` / `RAG_EMBEDDING_MODEL`
  - 硅基流动示例：`https://api.siliconflow.cn/v1` + `BAAI/bge-m3`
  - DeepSeek 无 embeddings，聊天用 DeepSeek 时必须单独配 embedding
- **重排**：硅基流动 `POST /rerank`，默认 `BAAI/bge-reranker-v2-m3`（复用 embedding 的 Key/Base；可用 `RAG_RERANK_MODEL` 覆盖）

## API 一览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 探活 |
| POST/GET | `/v1/kb` | 创建 / 列表知识库 |
| GET | `/v1/kb/{kb_id}` | 知识库详情 |
| POST | `/v1/kb/{kb_id}/documents` | multipart 上传 |
| GET | `/v1/documents/{doc_id}` | 文档详情 |
| DELETE | `/v1/documents/{doc_id}` | 删除文档（文件+chunks+索引） |
| POST | `/v1/documents/{doc_id}/reindex` | 按磁盘文件重解析索引 |
| GET | `/v1/kb/{kb_id}/documents` | 文档列表 |
| POST | `/v1/retrieve` | 混合召回（支持 `filters.doc_ids`、`rerank`） |
| POST | `/v1/eval/run` | 黄金集评测（通过/失败报告） |
| GET | `/` · `/admin` | 管理上传页（独立服务）；统一服务见 `/kb/` |

## 评测（Task 8）

先入库含「退款」的文档（管理页或 API），再任选其一：

```powershell
# API
curl -X POST http://127.0.0.1:8000/v1/eval/run `
  -H "Content-Type: application/json" `
  -d "{\"kb_id\":\"kb_default\"}"

# CLI（仓库根目录）
python -m rag_service.eval.run_cli --kb-id kb_default
```

黄金集：`rag_service/eval/golden.json`（问句 → `expect_any_source_contains` / `expect_any_text_contains`）。

## 范围（P0 / P1）

| 层级 | 能力 |
|------|------|
| P0 | KB CRUD、上传入库、FTS+向量召回、管理页 |
| P1 | Rerank、删除/重索引、`filters.doc_ids`、黄金集评测 |

任务清单：`openspec/changes/self-hosted-rag-mvp/tasks.md`
