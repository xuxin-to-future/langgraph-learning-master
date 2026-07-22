# 统一服务入口（单端口）

**日期：** 2026-07-22  
**状态：** 已确认并实施  

## 决策

- 单进程、单端口（默认 8000）
- `/` 客服对话；`/kb` 知识库管理
- 客服 API 与 RAG API 均挂在 `/v1/...`（路径无冲突）
- 包结构：新增 `app/` 组装层；`customer_service/`、`rag_service/` 保留为域包

## 启动

```powershell
uvicorn app.main:create_app --factory --reload --port 8000
```

## 配置

`RAG_PROVIDER=http`，`RAG_BASE_URL=http://127.0.0.1:8000`（同服自调用）。
