# RAG 切片策略升级（对齐 RAGFlow naive + 最佳实践）

**日期：** 2026-07-22  
**范围：** `rag_service` 文本切片（`.md` / `.txt`）  
**状态：** 已实现（2026-07-22）  
**关联：** `docs/superpowers/specs/2026-07-21-self-hosted-rag-mvp.md`、change `self-hosted-rag-mvp`

---

## 1. 目标与非目标

### 目标

- 切片行为对齐 RAGFlow **naive / TokenChunker** 主路径（非 TitleChunker）。
- 使用 **tiktoken `cl100k_base`** 计量 token；默认块大小 **512**。
- 默认块间 **10%** 字符后缀 overlap（可配置）。
- 识别 Markdown `#`～`######`；**短标题（&lt;50 token）强制并入下一段正文**。
- 上传与 `reindex` 共用同一 `split_text`；已入库文档需手动重索引生效。

### 非目标（本期不做）

- TitleChunker 祖先标题路径、父子 chunk（parent–child）。
- 表格/代码围栏完整保护（可列为后续增强）。
- 自动全库重切、管理页切片参数 UI。
- 从 RAGFlow 源码直接拷贝 `naive_merge`（保持本仓独立）。

---

## 2. 决策摘要

| 决策 | 选择 | 理由 |
|------|------|------|
| 实现路径 | 轻量移植 naive_merge 语义到 `chunking.py` | 行为接近、依赖可控 |
| 计量单位 | tiktoken `cl100k_base` | 与 RAGFlow 一致 |
| 默认大小 | 512 token | RAGFlow 产品默认 |
| 默认 overlap | 10% | 边界召回更稳（优于上游默认 0） |
| 标题 | `#`～`######` + 短标题合并 | 对齐 RAGFlow MD 处理 |
| 旧配置 | `RAG_CHUNK_MAX_CHARS` 弃用或仅硬兜底 | 避免双标准 |

---

## 3. 切片流水线

```text
原文
  → 规范化换行
  → 拆成小段（MD 标题行、空行段落、中英文句末标点可选）
  → 短标题（^#{1,6}\s+ 且 token < 50）并入下一段
  → 按 token 预算打包：当前块 token > 512 * (100 - overlap%) / 100 时新开块
  → 新块前缀 = 上一块文本的末尾 overlap% 字符后缀 + 本段
  → 输出 list[TextPiece(text, heading, position)]
```

### 行为约定

1. **heading**：取本块关联的最近标题文本（无则空字符串）；展示用，不单独作为空块。
2. **超长单段**：单段自身超过 512 token 时，按 token（或近似字符）硬切，并在切点尽量靠近换行。
3. **空内容**：strip 后为空的段丢弃。
4. **纯文本 `.txt`**：无 `#` 标题时，按空行/句末拆段后同样走 token 打包。

---

## 4. 配置

| 环境变量 | 默认 | 说明 |
|----------|------|------|
| `RAG_CHUNK_TOKEN_NUM` | `512` | 目标块 token 上限相关阈值 |
| `RAG_CHUNK_OVERLAP_PERCENT` | `10` | 0–90；与 RAGFlow `overlapped_percent` 同语义 |
| `RAG_CHUNK_MAX_CHARS` | 可选保留 | 仅作单段硬切绝对上限兜底；文档标明 deprecated |

`Settings` 增加 `chunk_token_num`、`chunk_overlap_percent`；`ingest` / `reindex` 传入 `split_text(..., max_tokens=..., overlap_percent=...)`。

依赖：`requirements.txt` 增加 `tiktoken`。

---

## 5. 代码落点

| 文件 | 变更 |
|------|------|
| `rag_service/services/chunking.py` | 重写 `split_text`；增加 token 计数、短标题合并、overlap 打包 |
| `rag_service/config/settings.py` | 新配置项 |
| `rag_service/services/ingest.py` | 使用新参数调用 `split_text` |
| `requirements.txt` | `tiktoken` |
| `rag_service/README.md` | 说明切片策略与重索引 |
| `tests/rag_service/test_ingest_api.py` 或新建 `test_chunking.py` | 单测覆盖 |

对外 API / DB schema **不变**（仍是 chunks 表字段）。

---

## 6. 测试计划

1. 短 `#` / `##` 标题 + 正文 → 标题不单独成块；块文本含标题上下文。
2. 长文 → 多数块 token ≤ 512（末块可更小）；块数 &gt; 1。
3. `overlap_percent=10` → 相邻两块存在后缀/前缀重叠。
4. 既有「退款政策」上传用例仍 `ready` 且 `chunk_count ≥ 1`。
5. 管理页对旧文档点「重索引」后切片反映新策略。

---

## 7. 迁移说明

- 已上传文档：**不会**自动重切；用户在管理页点「重索引」或重新上传。
- README 写明：升级切片后建议对重要知识库执行重索引。

---

## 8. 验收标准

- [ ] 默认配置下切片逻辑与上述流水线一致。
- [ ] 无 Key 时入库仍成功（embedding 跳过与切片无关）。
- [ ] 单测通过；退款类 md 仍可 keyword 召回。
- [ ] README 已更新切片与配置说明。
