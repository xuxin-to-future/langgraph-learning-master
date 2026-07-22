## 为什么（Why）

`customer_service/` 已按设计落地包骨架与契约，但节点、服务、API 仍为 `NotImplementedError`，无法演示 FAQ / 工单 / 转人工完整链路。需要按 **LangGraph StateGraph（Supervisor 路由）** 实现一期 MVP，把教学示例能力升级为可本地演示的客服系统。

## 变更内容（What Changes）

- 实现由 `SupportState` 驱动的 **StateGraph**：`supervisor` → 条件边 → `faq` | `ticket` | `chitchat` | `escalate`
- 实现 FAQ 检索（一期关键词；可选向量）与工单 SQLite 读写
- 实现 escalate 的 LangGraph **`interrupt` / `Command(resume)`** 人机协同，配合 Checkpointer（`thread_id` = `sessionId`）
- 实现 FastAPI：`POST /v1/chat`、`GET /health`、工单查询、人工 resume；API 层不写业务分支
- 无 `OPENAI_API_KEY` 时，规则路由 + 模板/关键词降级可跑通三验收场景
- 补齐确定性单测 / API 冒烟测试；可选后续：真实 LLM、SSE（不阻断本期）

**非目标（不做）：** 电商订单/物流、真实 IM/企微对接、多租户计费、运营后台 UI、评测平台、改写 `examples/`。

## 能力（Capabilities）

### 新增能力

- `support-graph`：LangGraph Supervisor 图编排、State、条件路由、编译与调用
- `faq-rag`：知识库检索与 FAQ 回答（含离线关键词路径）
- `tickets`：本地 SQLite 工单创建与查询
- `hitl-escalate`：转人工 interrupt / resume 与会话 checkpoint
- `chat-api`：FastAPI 会话契约、`sessionId`→`thread_id`、健康检查与管理辅助接口

### 修改中的能力

- （无）主库 `openspec/specs/` 尚无既有能力；本期全部为新增

## 影响范围（Impact）

- **代码：** `customer_service/**`（graph / services / tools / api / config / models）、`tests/customer_service/**`
- **依赖：** 现有 `langgraph`、`langchain-*`；新增/确认 `fastapi`、`uvicorn`、`httpx`（测试）、SQLite（标准库）
- **数据：** `data/tickets.db`（gitignore）、可选 `data/chroma/`
- **文档对齐：** `docs/superpowers/specs/2026-07-19-customer-service-design.md`
- **不影响：** `examples/`、`autogen/`
