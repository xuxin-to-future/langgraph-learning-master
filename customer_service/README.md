# customer_service

通用企业智能客服演示包（LangGraph Supervisor + FastAPI）。

设计规格：[`docs/superpowers/specs/2026-07-19-customer-service-design.md`](../docs/superpowers/specs/2026-07-19-customer-service-design.md)

OpenSpec 任务：[`openspec/changes/implement-customer-service-mvp/`](../openspec/changes/implement-customer-service-mvp/)

## 一键启动（推荐）

API 与前端由同一进程提供（静态页挂在 `/`）：

```powershell
cd d:\langgraph-learning-master
uvicorn customer_service.api.app:create_app --factory --reload --port 8000
```

浏览器打开：http://127.0.0.1:8000/

试着发送：

- `退款政策是什么？` → FAQ
- `帮我建一个无法登录的工单` → 工单
- `我要投诉，找人工` → 转人工，页面可填说明后恢复

## 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 探活 |
| POST | `/v1/chat` | 对话（`sessionId` + `message`） |
| GET | `/v1/tickets/{ticket_id}` | 查工单 |
| POST | `/v1/admin/escalate/{sessionId}/resume` | 人工 resume |

## 会话与 Checkpointer

- HTTP：`sessionId` → Python：`session_id` → LangGraph：`configurable.thread_id`
- 工厂：`get_checkpointer()` / `thread_config(session_id)`
- 默认内存；持久演示：`CHECKPOINTER_BACKEND=sqlite`

## 配置

见仓库根目录 `.env` / `.env.example`（DeepSeek 等 OpenAI 兼容接口）。

无 Key 时规则路由 + 关键词 FAQ 仍可跑通。

## 测试

```powershell
python -m pytest tests/customer_service -q
```
