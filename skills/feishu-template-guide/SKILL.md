---
name: feishu-template-guide
description: |
  openclaw-feishu-delivery 项目的飞书消息模板创建与发送指南。
  配置驱动架构：所有模板定义在 JSON 配置文件中，代码只负责通用渲染和发送。
  Use when: (1) 创建新的飞书消息模板, (2) 修改现有模板的卡片布局或路由,
  (3) 首次使用 openclaw-feishu-delivery 项目需要了解架构和使用方法,
  (4) 发送飞书卡片消息, (5) 调试模板渲染或发送失败。
  Triggers: "飞书模板", "feishu template", "创建模板", "新增飞书消息",
  "发送飞书", "send feishu", "卡片消息", "openclaw-feishu-delivery"。
---

# Feishu Template Guide

## 架构概览

```
Agent 产出 payload (data)
    ↓
feishu-templates.local.json 定义 blocks + route
    ↓
renderer.py 通用渲染引擎
    ↓
core.py 路由解析 + 飞书 API 发送
```

核心原则：**代码是通用引擎，业务全在 JSON 配置里**。

- `feishu-templates.local.json` — 模板注册表（blocks 定义 + 路由配置）
- `accounts.local.json` — 飞书应用凭证
- `scaffold-layouts.json` — 预定义布局骨架

## 新用户快速上手

### 1. 初始化 runtime

```bash
python3 scripts/bootstrap_runtime.py
```

从 `examples/` 复制示例配置到 `runtime/`，然后编辑：

- `runtime/accounts.local.json` — 填入飞书应用的 `app_id` 和 `app_secret`
- `runtime/feishu-templates.local.json` — 按需添加模板

accounts 结构：

```json
{
  "accounts": {
    "default": { "app_id": "cli_xxx", "app_secret": "xxx" },
    "my-agent": { "app_id": "cli_yyy", "app_secret": "yyy" }
  }
}
```

### 2. 发送测试消息

```bash
python3 scripts/send_message.py \
  --mode template \
  --template "模板名" \
  --agent-id "账号名" \
  --data '{"title":"测试","summary":"验证发送","timestamp":"2026-03-22 10:00"}'
```

## 创建新模板（标准流程）

### Step 1: scaffold 生成骨架

```bash
python3 scripts/scaffold_agent_task.py \
  --template-name my-report \
  --template-description "我的日报" \
  --agent-id my-agent \
  --job-name "my-daily-report" \
  --layout generic \
  --target-id oc_xxxxx \
  --channel topic \
  --cron "0 9 * * *"
```

scaffold 一次性完成三件事：

1. 在 `feishu-templates.local.json` 中插入模板定义（含 blocks + route）
2. 在 `jobs-spec.local.json` 中插入定时任务
3. 在 `runtime/payloads/` 生成示例 payload 文件

**scaffold 参数说明**：见 [references/scaffold-cli.md](references/scaffold-cli.md)

### Step 2: 定制 blocks

scaffold 生成的是通用骨架，需要根据业务调整 `feishu-templates.local.json` 中的 `presentation.blocks`。

**模板 JSON 顶层结构**：

```json
{
  "templates": {
    "my-report": {
      "description": "我的日报",
      "header_template": "blue",
      "required_fields": ["title", "summary", "timestamp", "thread_summary"],
      "presentation": {
        "schema": "1.0",
        "structure": "generic",
        "blocks": [ ... ]
      },
      "route": {
        "transport": { "provider": "feishu", "account": "my-agent" },
        "target": { "id": "oc_xxxxx", "type": "chat_id" },
        "delivery": { "channel": "topic" },
        "policy": { "lock_target": true, "lock_delivery": true },
        "thread": { ... }
      }
    }
  }
}
```

各字段说明：

| 字段 | 必填 | 说明 |
|------|------|------|
| `description` | 是 | 模板描述 |
| `header_template` | 是 | 卡片头部颜色：blue/wathet/turquoise/green/yellow/orange/red/carmine/violet/purple/indigo/grey |
| `required_fields` | 是 | payload 必须包含的字段列表，发送前自动校验 |
| `presentation.schema` | 是 | 渲染版本：`1.0`（线性）或 `2.0`（支持折叠面板） |
| `presentation.structure` | 是 | 布局族：见下方可选值 |
| `presentation.blocks` | 是 | block 数组，决定卡片内容 |
| `route` | 是 | 发送路由配置 |

**structure 可选值**：

| 值 | 适用场景 |
|----|----------|
| `generic` | 通用线性报告（markdown + facts + list） |
| `collapsible-list` | 多段折叠（日报、知识整理） |
| `grouped-panels` | 按分类展开面板（按 agent/分组） |
| `panel-report` | 巡检诊断报告 |

**block 类型速查**：见 [references/block-types.md](references/block-types.md)

### Step 3: 验证发送

```bash
python3 scripts/send_message.py \
  --mode template \
  --template "my-report" \
  --agent-id my-agent \
  --data '{"title":"测试日报","summary":"验证模板渲染","timestamp":"2026-03-22 09:00","thread_summary":{"notice":"测试完成","bullets":["验证通过"]}}'
```

成功标志：输出含 `✅ 群话题消息发送成功`。

### Step 4: 同步定时任务到 OpenClaw

```bash
python3 scripts/sync_openclaw_jobs.py \
  --spec-file runtime/jobs-spec.local.json \
  --apply
```

## 路由配置详解

### route.transport

```json
{ "provider": "feishu", "account": "my-agent" }
```

`account` 对应 `accounts.local.json` 中的 key。

### route.target

```json
{ "id": "oc_xxxxx", "type": "chat_id" }
```

| type | 说明 |
|------|------|
| `chat_id` | 群聊 ID（`oc_` 开头） |
| `open_id` | 用户 open_id（`ou_` 开头），用于私聊 |

### route.delivery

```json
{ "channel": "topic" }
```

| channel | 说明 |
|---------|------|
| `topic` | 群内固定话题（推荐，自动创建话题并追加消息） |
| `message` | 群内普通消息 |
| `direct` | 私聊（仅支持 open_id/union_id/user_id/email） |

### route.thread（仅 topic 通道）

```json
{
  "enabled": true,
  "binding_key_template": "agent:template-name",
  "title_template": "【模板标题】",
  "recreate_on_root_missing": true,
  "summary_reply": {
    "enabled": true,
    "required": true,
    "channel": "text",
    "mention_open_ids": ["ou_xxxxx"]
  }
}
```

- `binding_key_template` — 话题唯一标识，支持 `{date}` 等占位符
- `summary_reply` — 卡片发送后自动追加文字摘要回复
- `mention_open_ids` — 摘要中 @ 的用户

### route.policy

```json
{ "lock_target": true, "lock_delivery": true }
```

锁定后 CLI 参数不能覆盖 target 和 channel，确保消息始终发到正确的群。

## 飞书卡片限制

- 每张卡片最多 **4 个 table**，超出会报错 `card table number over limit`
- 如果数据较多，优先用 `record_list` 替代 `table`
- `collapsible_panel` 不支持嵌套

## Agent 发送消息的标准方式

Agent 完成业务后，调用项目脚本发送：

```bash
python3 /path/to/openclaw-feishu-delivery/scripts/send_message.py \
  --mode template \
  --job-id "{{job_id}}" \
  --jobs-file "/path/to/jobs.json" \
  --templates-file "/path/to/runtime/feishu-templates.local.json" \
  --accounts-file "/path/to/runtime/accounts.local.json" \
  --agent-id my-agent \
  --template "my-report" \
  --data '{ ... payload JSON ... }'
```

**禁止**在 Agent 脚本中直接构造飞书 Card JSON 或调用飞书 API。所有消息必须通过模板系统发送。

## Python API 调用

```python
from openclaw_feishu_cron_kit.core import build_settings, send_template_payload

settings = build_settings(project_root=Path("/path/to/project"))
result = send_template_payload(
    settings,
    template_name="my-report",
    data={"title": "...", "summary": "...", "timestamp": "..."},
    agent_id="my-agent",
)
```

## 文件路径索引

| 文件 | 用途 |
|------|------|
| `runtime/feishu-templates.local.json` | 模板注册表（blocks + route） |
| `runtime/accounts.local.json` | 飞书应用凭证 |
| `runtime/scaffold-layouts.json` | 预定义布局骨架 |
| `runtime/jobs-spec.local.json` | OpenClaw 定时任务定义 |
| `scripts/send_message.py` | CLI 发送入口 |
| `scripts/scaffold_agent_task.py` | 模板脚手架 |
| `scripts/sync_openclaw_jobs.py` | 同步任务到 OpenClaw |
| `examples/` | 脱敏示例配置，可作为参考 |
| `docs/presentation-schema.md` | Presentation 层 DSL 文档 |
