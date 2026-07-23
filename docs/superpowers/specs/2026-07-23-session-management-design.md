# 完整会话管理设计（2026-07-23）

## 目标

按市面通行做法（Conversational RAG + 轻量 Dialogue State）补齐会话管理：持久化、窗口+摘要、新会话、追问指代、会话回忆、工作记忆、检索门控。为日后槽位引导成答（方案 B）预留字段，本轮不实现 B 的引导逻辑。

## 已确认决策

- 架构：**方案 A** — `session` 层与 `supervisor` 业务意图层分离
- 覆盖能力：1–7 全部（持久化、压缩、重置、追问、回忆、工作记忆、检索策略）
- 现有业务意图不变：`faq` / `ticket` / `chitchat` / `escalate`
- B（槽位采集）：仅预留 `session_memory.slots` 与 `turn_type=slot_fill` 枚举位，本轮不产出、不引导
- 对外：`sessionId` 不变；响应增加 `turnType`、`needRetrieve`（可选调试 `standaloneQuery`）

## 图结构

```
START → session → supervisor → {faq | ticket | chitchat | escalate} → END
```

- `turn_type == session_recall` → 强制走 `chitchat`（回忆模式），不查库
- 其余按 supervisor 的 `intent` 路由

## turn_type

| 值 | 含义 | need_retrieve |
|----|------|---------------|
| `new_question` | 新业务问 | true |
| `followup` | 追问/指代/深化 | true（用改写问句） |
| `session_recall` | 回忆本会话说过什么 | false |
| `topic_switch` | 换话题 | true（更新 topic） |
| `clarify` | 澄清确认 | false（默认） |
| `other` | 寒暄等 | false |
| `slot_fill` | 预留 B | 本轮不使用 |

## 状态字段

```text
conversation_summary          # 已有
session_memory:
  topic: str
  entities: list[str]
  last_user_question: str
  last_assistant_answer: str  # 可截断
  slots: dict                 # 预留，本轮 {}
turn_type
need_retrieve: bool
standalone_query: str         # 独立检索问句
```

## 数据流

1. API 注入 `HumanMessage`（checkpointer 按 thread 续写）
2. **session**：超预算压缩 → 一次结构化 LLM（turn_type / need_retrieve / standalone_query / memory 增量）→ 失败则启发式降级
3. **supervisor**：只分类业务 intent（可读 turn_type 辅助；`session_recall` 仍可标 chitchat）
4. **叶子**：
   - FAQ：`need_retrieve` 门控；检索只用 `standalone_query`；生成带会话上下文；禁止二次改写 LLM
   - chitchat 回忆模式：根据 `last_user_question` / messages 复述
   - ticket / escalate：带上下文理解指代
5. 叶子结束回写 `last_user_question` / `last_assistant_answer`

## 降级

- session LLM 失败：有历史 → `followup` + 原文检索；无历史 → `new_question`；memory 启发式更新
- 压缩失败：保留旧 summary，窗口仍裁剪
- 检索失败：有上文则仅会话生成
- supervisor 失败：回退 chitchat（现状）

## 性能

常见 FAQ 追问：session×1 + supervisor×1 + 检索×1 + 生成×1。回忆/不检索：0 次检索。摘要仅超预算触发。

## 验收样例

1. 商机规则 → 「整理成计算公式」→ 承接上文出公式  
2. 「我刚才问的是什么？」→ 复述上一用户问，无强制引用  
3. 换话题后旧指代不绑旧 topic  
4. `/new` 后 memory/summary 为空  

## 明确不做

- 槽位引导、主动追问补全（B）
- 跨 session 用户画像
- 多 Agent 子图
