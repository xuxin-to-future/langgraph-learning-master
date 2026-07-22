## 1. 基础：配置 / 契约 / 依赖

- [x] 1.1 在 `requirements.txt` 增加 `fastapi`、`uvicorn`、`httpx`；确认 `langgraph` / `langchain-core` 版本与现有 examples 一致
- [x] 1.2 完善 `customer_service/config/settings.py`：从环境变量加载 `OPENAI_API_KEY`、`OPENAI_MODEL`、数据库/checkpointer 路径、`allow_offline_fallback`；提供 `get_settings()`
- [x] 1.3 将 `models/schemas.py` 升级为 Pydantic（保留 `sessionId` 别名），对齐 ChatRequest / ChatResponse / Ticket DTO
- [x] 1.4 复核 `models/state.py` 的 `SupportState` 与 Intent 字面量，必要时补充默认值约定（文档化即可）

## 2. 服务层 — 工单（SQLite）

- [x] 2.1 实现 `services/tickets.py`：初始化表结构、`create_ticket`、`get_ticket`；库文件落在 `data/tickets.db`（目录自动创建）
- [x] 2.2 实现 `tools/ticket_tools.py` 薄封装，供 ticket 节点调用
- [x] 2.3 单测：创建后可查询；不存在的 id 返回空或约定错误（不经过 HTTP）



## 3. 服务层 — FAQ / RAG（离线关键词优先）

- [x] 3.1 实现 `services/rag.py`：加载 `knowledge/*.md`，关键词/简单打分检索，返回片段与来源文件名
- [x] 3.2 实现离线 `answer_with_context`（模板拼接检索片段，不调用 LLM）
- [x] 3.3 实现 `tools/kb_search.py` 薄封装
- [x] 3.4 单测：查询「退款政策」命中 `support-policy.md`



## 4. 服务层 — 记忆 / Checkpointer（LangGraph 持久化）

- [x] 4.1 实现 `services/memory.py`：`get_checkpointer()` 默认返回 `MemorySaver`，可配置为 `SqliteSaver`
- [x] 4.2 约定 `thread_id` 与对外 `sessionId` 一一对应（文档 + 调用约定，逻辑在 API）



## 5. 图节点 — LangGraph Node 实现

- [x] 5.1 实现 `nodes/supervisor.py`：规则意图分类（faq/ticket/chitchat/escalate）；无 Key 时强制走规则；有 Key 时可选用 LLM，失败回退规则
- [x] 5.2 实现 `nodes/faq.py`：调用 RAG → 写入 `retrieved_docs` / `answer`（可选把引用写进 answer 或扩展字段）
- [x] 5.3 实现 `nodes/ticket.py`：解析用户诉求摘要 → `create_ticket` → 写入 `ticket_id` / `answer`
- [x] 5.4 实现 `nodes/chitchat.py`：短模板或轻量回复，写入 `answer`
- [x] 5.5 实现 `nodes/escalate.py`：写入 `needs_human=True`，调用 LangGraph `interrupt`；按需实现 `tools/escalate_tool.py`
- [x] 5.6 单测 supervisor 关键词路由表（对齐三验收话术）



## 6. 图组装 — StateGraph 编译

- [x] 6.1 在 `graph/builder.py` 创建 `StateGraph(SupportState)`，注册 supervisor/faq/ticket/chitchat/escalate 节点
- [x] 6.2 入口设为 supervisor；用现有 `route_by_intent` 做 `add_conditional_edges` 映射到四节点；各技能节点连到 END
- [x] 6.3 `compile(checkpointer=get_checkpointer())`；导出 `build_graph()`（可选模块级懒加载单例）
- [x] 6.4 图级集成测试（不经 HTTP）：三验收输入 → 断言 intent/answer/ticket_id/needs_human（可 mock interrupt/resume）



## 7. 对话 API — FastAPI 接入 LangGraph

- [x] 7.1 实现 `api/app.py`：`create_app()` 注册路由与 `/health`
- [x] 7.2 实现 `api/routes_chat.py`：`POST /v1/chat` 校验 → `thread_id=session_id` → `graph.invoke` → 映射为 ChatResponse
- [x] 7.3 实现 `GET /v1/tickets/{ticket_id}`（可放在 admin 或 chat 模块，路径保持设计不变）
- [x] 7.4 错误映射：缺 sessionId/空消息 → 400；工单写失败 → 500；等待人工 → 200+needs_human；未知异常不向客户端抛栈
- [x] 7.5 替换 `tests/customer_service/test_api_smoke.py`：health + chat FAQ 场景返回 200



## 8. 人机协同管理 — interrupt / resume

- [x] 8.1 实现 `api/routes_admin.py`：`POST /v1/admin/escalate/{sessionId}/resume`，使用 `Command(resume=...)` 与同一 `thread_id`
- [x] 8.2 端到端测试：escalate 暂停 → resume → 得到最终 answer
- [x] 8.3 对照 `examples/05_human_in_the_loop.py` 核对 API 用法，避免版本偏差



## 9. 验收加固

- [ ] 9.1 固化三场景测试与示例请求（文档或参数化测试）：退款 FAQ / 无法登录工单 / 投诉转人工
- [ ] 9.2 同一 `sessionId` 两轮对话，断言 messages/checkpoint 保留上下文
- [ ] 9.3 更新 `customer_service/README.md`：如何启动 uvicorn、如何跑测试、离线模式说明
- [ ] 9.4 确认 `data/` 已在 `.gitignore`；必要时补 `.gitkeep` 或启动时创建目录



## 10. 可选后续（不阻断 MVP）

- [ ] 10.1 可选：supervisor/faq 真实 LLM 路径（有 Key 时），失败回退离线
- [ ] 10.2 可选：`POST /v1/chat/stream` SSE（节点级 updates）
- [ ] 10.3 可选：Chroma 向量检索与 reindex 管理接口