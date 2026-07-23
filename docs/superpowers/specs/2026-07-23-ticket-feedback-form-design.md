# 工单反馈表单设计（2026-07-23）

## 目标

吐槽/反馈/报障时弹出表单创建工单；同时提供常驻「提交反馈」入口。转人工（escalate）流程不变。

## 已确认决策

- 触发：主动入口 + 对话 `ticket` 意图弹窗（不自动建单）
- 问题类型（多选）：业务问题、系统 Bug、个人反馈、功能建议、其他（至少选 1）
- 描述：必填；对话触发时不预填
- 附件：最多 3 张，单张 ≤ 2MB，jpg/png/webp/gif；经后端上传阿里云 OSS（`cs/` 前缀）
- 评分：1–5 星必填，文案 很差/较差/一般/较好/很好
- 提交人：固定 `admin`（暂无登录）

## 架构（方案 1）

1. `ticket` 节点只提示填表，返回 `needs_ticket_form=true`，不写库
2. `POST /v1/tickets/attachments`：图片 → OSS → 返回 URL
3. `POST /v1/tickets`：类型/描述/评分/附件 URL/`sessionId`/`reporter=admin` → SQLite
4. 前端模态表单：常驻按钮 + 对话 `needs_ticket_form` 时打开

## 数据模型扩展

`tickets` 表新增：`problem_types`（JSON）、`attachments`（JSON）、`rating`（1–5）、`reporter`（默认 admin）。`subject` 由描述截断生成。

## 安全

OSS 密钥仅来自环境变量 / `.env`，不得提交仓库。
