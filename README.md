# 智服助手 · 智能客服 + 知识库

基于 **LangGraph Supervisor + FastAPI** 的企业智能客服演示；知识库与对话**同端口**统一服务。

## 功能

- FAQ 知识库问答（检索 + 流式大模型生成）
- 知识库管理页（上传 / 重索引 / 删除）
- 工单创建 / 查询（本地 SQLite）
- 转人工（`interrupt` / resume）

## 环境准备

```powershell
cd d:\langgraph-learning-master
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# 编辑 .env，填入 OPENAI_* / RAG_EMBEDDING_* 等
```

## 启动（统一入口 · 推荐）

```powershell
uvicorn app.main:create_app --factory --reload --port 8000
```

| 地址 | 说明 |
|------|------|
| http://127.0.0.1:8000/ | 客服对话（右上角「知识库」入口） |
| http://127.0.0.1:8000/kb/ | 知识库管理 |
| http://127.0.0.1:8000/health | 探活 |

`.env` 建议：

```env
RAG_PROVIDER=http
RAG_BASE_URL=http://127.0.0.1:8000
RAG_KB_ID=kb_default
```

## 分服务调试（可选）

仍可用独立工厂分别起 8000 / 8100：

```powershell
uvicorn customer_service.api.app:create_app --factory --reload --port 8000
uvicorn rag_service.api.app:create_app --factory --reload --port 8100
```

## 接口（同服）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 探活 |
| POST | `/v1/chat` · `/v1/chat/stream` | 对话 / SSE |
| GET | `/v1/tickets/{ticket_id}` | 查工单 |
| POST | `/v1/admin/escalate/{sessionId}/resume` | 人工恢复 |
| POST/GET | `/v1/kb` · `/v1/documents` · `/v1/retrieve` | 知识库 API |
| POST | `/v1/eval/run` | 黄金集评测 |

## 目录

```text
app/                  # 统一入口 create_app
customer_service/     # 客服域（图 · API · 对话页）
rag_service/          # 知识库域（入库 · 召回 · 管理页）
tests/
docs/superpowers/specs/
openspec/
data/
```

更多说明见 [`customer_service/README.md`](customer_service/README.md)、[`rag_service/README.md`](rag_service/README.md)。
