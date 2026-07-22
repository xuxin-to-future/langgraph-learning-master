## 背景

设计规格见 `docs/superpowers/specs/2026-07-21-self-hosted-rag-mvp.md`。客服已可演示，知识入库能力不足。本变更交付独立 `rag_service`，并以 **上传页落成知识库** 为可用性门槛。

## 目标 / 非目标

**目标：**

- P0：kb + 上传 md/txt + 切片索引 + retrieve + health + 管理上传页
- P1：rerank、文档生命周期、retrieve 过滤、简单评测
- 契约稳定，便于客服后续 `RAG_PROVIDER=http`

**非目标：** 全格式解析、多租户、复杂权限、客服图大改（仅预留客户端任务）

## 决策

### D1 — 同仓独立服务

- 包名：`rag_service/`
- 启动：`uvicorn rag_service.api.app:create_app --factory --port 8100`
- 与客服分离端口，避免静态路由冲突

### D2 — 存储

| 内容 | 一期 |
|------|------|
| 元数据（kb/doc/chunk） | SQLite `data/rag/rag.db` |
| 原始文件 | `data/rag/files/{kb_id}/{doc_id}/...` |
| 关键词索引 | SQLite FTS5 或表内简单倒排（实现可选） |
| 向量 | 本地文件/sqlite 存 embedding；模型读 `.env` |

### D3 — 入库流水线

```text
上传 → Document(status=pending)
    → 解析文本 → 按 ##/段落切片
    → 写 Chunk → 建关键词（+向量）索引
    → status=ready | failed
```

一期默认同步处理（小文件）；接口预留异步字段。

### D4 — 管理页（必须）

- 路径建议：`http://127.0.0.1:8100/` 或 `/admin`
- 功能：选/建知识库、上传文件、列表显示 status/chunk_count、失败原因、删除（P1 可完善）
- 实现：静态 HTML + 调本服务 API（与客服页风格可简化，不求华美）

### D5 — 召回

- `POST /v1/retrieve`：keyword + vector 融合（RRF 或加权）
- 返回 `RetrievedChunk` 字段与设计规格一致
- P1：`rerank`、`filters.doc_ids`

### D6 — 与客服

- 本变更 tasks 末尾增加「适配客户端」可选组；默认不切换客服流量

## 风险 / 取舍

| 风险 | 缓解 |
|------|------|
| 向量模型依赖外网/Key | P0 关键词先可用；无 Key 时向量跳过仍可 retrieve |
| 大文件阻塞 | 限制扩展名与大小；后续再异步 |
| 与客服 knowledge 双源 | 文档标明；对接完成前客服仍用 local |

## 落地顺序

1. 包骨架 + 模型 + SQLite  
2. kb/doc API + 切片索引  
3. 上传 API + 管理页（**可用性门槛**）  
4. retrieve 混合召回  
5. P1：rerank / 删除更新 / 过滤 / 评测  
6. 客服 http 客户端（可选）
