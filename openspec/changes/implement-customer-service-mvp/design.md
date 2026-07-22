## 背景

仓库已有 LangGraph 教学示例（`examples/`）与客服设计规格（`docs/superpowers/specs/2026-07-19-customer-service-design.md`）。`customer_service/` 目录与契约已齐，实现几乎全是占位。本期把骨架补成可演示 MVP，技术主轴是 **LangGraph StateGraph + Supervisor 条件路由 + Checkpointer + interrupt 人机协同**。

现状要点：

- 已有：`SupportState`、`route_by_intent`、knowledge/prompts、settings 路径；测试仅覆盖 router 与「create_app 未实现」
- 未有：节点逻辑、`build_graph`、RAG/tickets/memory、FastAPI 路由

## 目标 / 非目标

**目标：**

- 三验收场景可复现：FAQ 退款政策、创建工单、转人工
- 同一 `sessionId` 多轮不丢（Checkpointer + `thread_id`）
- 无 API Key 可降级跑通主路径
- 分层清晰：api 无业务分支；graph 只编排；services 承载领域逻辑

**非目标：**

- 电商订单/物流、真实工单/IM、多租户、完整后台 UI、评测平台
- 改写 `examples/`；本期不强制 SSE / 向量库 / 真实 LLM（可作为后续任务）

## 决策

### D1 — 编排：Supervisor StateGraph（非单 Agent 工具循环）

```text
START → supervisor → (route_by_intent)
                      ├─ faq → END
                      ├─ ticket → END
                      ├─ chitchat → END
                      └─ escalate → interrupt → (resume) → END
```

- **为何：** 路由可单测、路径可观测，贴合客服 SOP；与设计 §2.1 一致。
- **对照 AutoGen：** 类似 Selector，但边与 State 由代码显式定义，确定性更强。

### D2 — State 与边

- 复用 `SupportState`；`messages` 使用 `add_messages`
- `edges.route_by_intent` 已存在，builder 使用 `add_conditional_edges("supervisor", route_by_intent, {...})`
- 节点只写职责内字段（supervisor→intent；faq→retrieved_docs/answer；等）

### D3 — 离线优先，再挂 LLM

1. 规则 supervisor（关键词：退款/政策→faq；工单/无法登录→ticket；投诉/人工→escalate；其余→chitchat）
2. FAQ 关键词检索 `knowledge/*.md`
3. 可选：读 `prompts/*.md` + `common.llm` 增强（失败回退离线）

### D4 — 持久化

| 能力 | 一期选择 |
|------|----------|
| 会话 | 默认 `MemorySaver`；配置开关可切 `SqliteSaver` |
| 工单 | SQLite `data/tickets.db` |
| 向量 | 可选；默认不做，避免阻塞 MVP |

### D5 — 人机协同（HITL）

- `escalate`：`needs_human=True` + `interrupt({...})`
- 管理接口：`Command(resume=payload)` + 同一 `thread_id`
- API 在等待人工时仍返回 **200** + `needs_human=true`

### D6 — API 契约

- 保持设计 §4：`sessionId` 别名、`ChatRequest`/`ChatResponse`
- schemas 可从 TypedDict 升级为 Pydantic（FastAPI 校验需要）——在 models 层完成，避免路由内散落校验逻辑

### D7 — 依赖

- `requirements.txt` 增加：`fastapi`、`uvicorn`、`httpx`（TestClient）
- LangGraph 已在仓库中

## 风险 / 取舍

| 风险 | 缓解 |
|------|------|
| 规则路由误分 | 验收用例固定话术；单测覆盖关键词表；后续再上 LLM supervisor |
| MemorySaver 进程重启丢会话 | 文档标明；演示长跑可开 SqliteSaver |
| interrupt API 随 LangGraph 版本差异 | 对齐本仓库 `examples/05_human_in_the_loop.py` 写法 |
| TypedDict→Pydantic 迁移 | 保持字段名与别名不变，先改 models 再接 API |
| 范围膨胀（SSE/向量/LLM） | tasks 中标为可选；MVP 不依赖 |

## 落地顺序

无生产数据迁移。实现顺序：

1. config + 可校验 schemas
2. services（tickets / rag / memory）
3. nodes + `build_graph`
4. FastAPI
5. HITL resume
6. 测试：将「未实现」断言替换为真实验收

## 开放问题

- 向量库是否二期再做 — **建议一期仅关键词**（与设计开放问题一致）
- SSE 事件格式 — **建议 MVP 不做**；同步 `/v1/chat` 足够演示
