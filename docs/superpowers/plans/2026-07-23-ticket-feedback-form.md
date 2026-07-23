# Ticket Feedback Form Implementation Plan

> **For agentic workers:** Implement task-by-task. Steps use checkbox syntax.

**Goal:** Chat + 常驻入口弹出工单表单，经 OSS 上传图片后创建扩展字段工单。

**Architecture:** ticket 节点返回 `needs_ticket_form`；独立 `POST /v1/tickets` + attachments；前端模态表单。

**Tech Stack:** FastAPI, SQLite, oss2, 现有静态 HTML/JS

## Global Constraints

- reporter 固定 admin；密钥仅环境变量；附件最多 3 / 2MB / 图片类型

## Tasks

- [x] Schema/settings/OSS/ticket service
- [x] API routes + ticket_node + ChatResponse
- [x] Frontend modal
- [x] Tests
