# 智能客服演示系统 — 设计规格

**日期：** 2026-07-19  
**状态：** 已审阅；包骨架已落地  
**范围：** 设计 + 空包结构；业务逻辑待实现  
**仓库：** `langgraph-learning`（与现有 `examples/` 并列）

---

## 1. 背景与目标

### 1.1 动机

在已完成 LangGraph 教学示例（StateGraph、工具循环、记忆、HITL、多智能体）的基础上，设计一套可本地演示的**通用企业智能客服**系统，形成从「示例」到「可演示产品骨架」的进阶路径。

### 1.2 目标（一期 MVP）

- 知识库 FAQ 问答（产品/政策文档）
- 工单创建与查询（本地 SQLite）
- 转人工（LangGraph `interrupt` / resume）
- FastAPI 对外提供对话与管理辅助接口
- 无 API Key 时可降级跑通主路径（规则路由 + 模板/关键词检索）

### 1.3 非目标（一期明确不做）

- 电商订单/物流 SQL
- 真实工单系统、IM、企微/钉钉对接
- 多租户、权限、计费、完整运营后台 UI
- 评测平台与复杂 Agent 网络
- 改写或合并现有 `examples/` 教学脚本

### 1.4 决策摘要

| 项 | 选择 |
|----|------|
| 用途 | 可演示完整客服链路（选项 B） |
| 业务场景 | 通用企业客服（非电商） |
| 本阶段交付 | 仅设计文档（选项 A） |
| 架构 | Supervisor 多智能体（方案 1） |
| 会话标识 | 对外 `sessionId`，对内映射 LangGraph `thread_id` |

### 1.5 参考项目（结构共性）

| 类型 | 参考 | 采纳点 |
|------|------|--------|
| LangGraph 客服 | AdaRAG、LangGraph-Customer-Support-Agent | Router → FAQ/Ticket/HITL 节点 |
| 企业分层 | smartcs-web、ai-customer-service | api / rag / memory / tools 分模块 |
| 知识库平台 | Dify 类结构 | `knowledge/` 与编排分离 |

---

## 2. 架构

### 2.1 选型结论

采用 **Supervisor 多智能体 + LangGraph StateGraph**，而非单 Agent+Tools（路由难测）或重度企业分层（对学习仓库过重）。

### 2.2 运行时分层

```text
┌─────────────────────────────────────────┐
│  api/          FastAPI（HTTP / SSE）      │
├─────────────────────────────────────────┤
│  graph/        LangGraph Supervisor 编排  │
│    router → faq | ticket | chitchat | escalate │
├─────────────────────────────────────────┤
│  services/     RAG / 工单 / 会话记忆       │
│  tools/        供节点调用的业务工具         │
│  models/       State、DTO、领域模型         │
├─────────────────────────────────────────┤
│  knowledge/    示例政策/产品文档           │
│  config/       设置、LLM、向量库开关        │
└─────────────────────────────────────────┘
```

### 2.3 目录树

```text
langgraph-learning/
├── examples/                         # 保持不动
├── common/                           # 可选复用 LLM 辅助
├── customer_service/                 # 智能客服演示系统（新建）
│   ├── __init__.py
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── state.py                  # SupportState
│   │   └── schemas.py                # API / 工单 Pydantic
│   ├── graph/
│   │   ├── __init__.py
│   │   ├── builder.py
│   │   ├── edges.py
│   │   └── nodes/
│   │       ├── supervisor.py
│   │       ├── faq.py
│   │       ├── ticket.py
│   │       ├── chitchat.py
│   │       └── escalate.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── rag.py
│   │   ├── tickets.py
│   │   └── memory.py
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── kb_search.py
│   │   ├── ticket_tools.py
│   │   └── escalate_tool.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── app.py
│   │   ├── routes_chat.py
│   │   └── routes_admin.py
│   ├── knowledge/
│   │   ├── product-overview.md
│   │   ├── billing-faq.md
│   │   └── support-policy.md
│   └── prompts/
│       ├── supervisor.md
│       └── faq.md
├── data/                             # 运行时数据（gitignore）
│   ├── chroma/
│   └── tickets.db
├── tests/
│   └── customer_service/
│       ├── test_router.py
│       └── test_api_smoke.py
└── docs/superpowers/specs/
    └── 2026-07-19-customer-service-design.md
```

### 2.4 模块职责

| 模块 | 职责 |
|------|------|
| `api` | 收发消息、SSE、校验；`sessionId` → `thread_id` 映射 |
| `graph` | 唯一编排入口：路由与节点 |
| `services` | RAG / 工单 / 记忆，无 HTTP |
| `tools` | 给节点/LLM 的薄封装 |
| `models` | State 与契约，避免循环依赖 |
| `knowledge` | 演示用知识源 |
| `config` | 集中配置，禁止散落读 env |

---

## 3. 数据流与 State

### 3.1 主链路

```text
Client
  │  POST /v1/chat  { sessionId, message }
  ▼
api.routes_chat
  │  config={"configurable": {"thread_id": sessionId}}
  ▼
graph.invoke / astream
  ▼
supervisor → intent ∈ {faq, ticket, chitchat, escalate}
  ├─ faq      → services.rag → answer + citations
  ├─ ticket   → services.tickets → ticket_id
  ├─ chitchat → 轻量回复
  └─ escalate → interrupt / needs_human
  ▼
API 返回 ChatResponse（含 sessionId）
```

### 3.2 SupportState

| 字段 | 类型思路 | 说明 |
|------|----------|------|
| `messages` | `Annotated[list, add_messages]` | 多轮对话 |
| `intent` | `Literal["faq","ticket","chitchat","escalate"]` | 路由结果 |
| `retrieved_docs` | `list[str]` | FAQ 检索片段 |
| `ticket_id` | `str \| None` | 工单产出 |
| `needs_human` | `bool` | 是否转人工 |
| `answer` | `str` | 本轮最终回复 |
| `error` | `str \| None` | 可恢复错误 |

原则：节点只写职责内字段；历史列表使用 reducer。

### 3.3 会话与 HITL

- Checkpointer：开发用 `MemorySaver`，持久化演示用 `SqliteSaver`
- 客户端必须传稳定 `sessionId`
- `escalate` 使用 `interrupt`；运营通过 `Command(resume=...)` 或管理接口继续

### 3.4 验收场景

1. **FAQ：**「退款政策是什么？」→ 命中 `support-policy.md`
2. **工单：**「帮我建一个无法登录的工单」→ 返回 `ticket_id`
3. **转人工：**「我要投诉，找人工」→ `needs_human=true`

---

## 4. API 契约与错误处理

### 4.1 接口一览

| 方法 | 路径 | 用途 |
|------|------|------|
| `POST` | `/v1/chat` | 同步对话 |
| `POST` | `/v1/chat/stream` | SSE 流式（实现阶段） |
| `GET` | `/v1/tickets/{ticket_id}` | 查询工单 |
| `POST` | `/v1/admin/escalate/{sessionId}/resume` | 人工 resume |
| `GET` | `/health` | 探活 |

二期可选：`POST /v1/admin/knowledge/reindex`。

### 4.2 会话字段命名

| 层 | 字段名 |
|----|--------|
| HTTP JSON | `sessionId` |
| Python / Pydantic | `session_id`（`alias="sessionId"`） |
| LangGraph config | `configurable["thread_id"] = session_id` |

### 4.3 请求 / 响应

**ChatRequest**

```json
{
  "sessionId": "user-42",
  "message": "退款政策是什么？",
  "metadata": {}
}
```

**ChatResponse**

```json
{
  "sessionId": "user-42",
  "intent": "faq",
  "answer": "...",
  "ticket_id": null,
  "needs_human": false,
  "citations": ["support-policy.md#refund"]
}
```

API 层只做校验与序列化，不写业务分支。

### 4.4 错误处理

| 场景 | 行为 |
|------|------|
| 缺 `sessionId` / 空消息 | `400`，不入图 |
| LLM / 嵌入失败 | 节点写 `error`；API `502` 或降级文案 |
| 知识库无命中 | `200` + 明确未找到，可建议建工单/转人工 |
| 工单写库失败 | `500`，不伪造 `ticket_id` |
| 等待人工 | `200` + `needs_human=true` |
| 未知异常 | 日志 + 通用错误，不向客户端抛栈 |

原则：可预期业务结果用 `200` + 字段；协议/基础设施失败用 4xx/5xx。

### 4.5 配置

- 沿用仓库 `.env`（如 `OPENAI_API_KEY`）
- 由 `customer_service.config.settings` 统一读取
- 无 Key：规则 supervisor + 关键词/模板降级

---

## 5. 测试与成功标准

### 5.1 测试策略

| 层级 | 覆盖点 |
|------|--------|
| 单元 | supervisor 路由；tickets 创建/查询 |
| 集成 | FAQ（mock LLM / 降级）；同 `sessionId` 多轮 |
| API | `/v1/chat`、`/health`（TestClient） |
| HITL | interrupt 后 resume |

CI 优先确定性路径；LLM 调用一律可 mock。

### 5.2 成功标准

1. 三个验收场景文档化可复现
2. 同一 `sessionId` 多轮上下文不丢
3. 目录与 §2.3 一致；路由层无业务渗入

---

## 6. 实现阶段建议顺序（供后续计划，本阶段不执行）

1. 包骨架与 `settings` / `SupportState` / schemas（含 `sessionId`）
2. 规则版 supervisor + 四节点最小闭环（无真实 LLM）
3. tickets SQLite + FAQ 关键词/向量检索
4. FastAPI `/v1/chat` 与 health
5. checkpointer + escalate HITL
6. 可选：真实 LLM、SSE、reindex

---

## 7. 开放问题（实现前可再定）

- 向量库默认选 Chroma 本地，还是一期仅关键词检索
- SSE 事件格式（按节点 vs 按 token）是否需与前端约定

（二者不影响本设计文档落地为「结构 + 契约」规格。）
