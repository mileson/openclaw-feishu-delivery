# Scaffold CLI Reference

`scripts/scaffold_agent_task.py` 一键生成模板 + 定时任务 + 示例 payload。

## 参数列表

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `--template-name` | 是 | - | 模板唯一标识（kebab-case） |
| `--template-description` | 是 | - | 模板描述（中文） |
| `--agent-id` | 是 | - | 执行 Agent 标识 |
| `--job-name` | 是 | - | 定时任务名称 |
| `--layout` | 是 | - | 布局类型（见下方） |
| `--target-id` | 是 | - | 目标群 chat_id 或用户 open_id |
| `--target-type` | 否 | `chat_id` | `chat_id` / `open_id` |
| `--channel` | 否 | `topic` | `topic` / `message` / `direct` |
| `--header-template` | 否 | `blue` | 卡片头部颜色 |
| `--transport-account` | 否 | 同 agent-id | 飞书应用账号名 |
| `--binding-key` | 否 | `{agent}:{template}` | 话题绑定 key |
| `--thread-title` | 否 | `【{description}】` | 话题标题 |
| `--mention-open-id` | 否 | - | 摘要中 @ 的用户（可多次） |
| `--schedule-kind` | 否 | `cron` | `cron` / `every` |
| `--cron` | 条件 | - | cron 表达式（schedule-kind=cron 时必填） |
| `--every` | 条件 | - | 间隔（schedule-kind=every 时必填） |
| `--tz` | 否 | `Asia/Shanghai` | 时区 |
| `--force` | 否 | - | 覆盖已存在的模板/任务 |
| `--disabled` | 否 | - | 创建但不启用 |

## 可用 layout

| layout | schema | 适用场景 | required_fields |
|--------|--------|----------|-----------------|
| `generic` | 1.0 | 通用线性报告 | title, summary, sections, timestamp |
| `items-report` | 1.0 | 候选项列表 | title, count, items, timestamp |
| `sections-report` | 1.0 | 多分区简报 | title, summary, sections, timestamp |
| `system-status` | 1.0 | 系统状态 | title, timestamp, overall_status, health_score |
| `distribution-summary` | 1.0 | 分发摘要 | title, timestamp, skill_name, source, target_agent, match_score |
| `collapsible-list` | 2.0 | 多段折叠 | title, summary, report_date, organized_at, execution_steps, ... |
| `knowledge-digest` | 2.0 | 知识整理 | 同 collapsible-list |
| `grouped-panels` | 2.0 | 按分组展开 | title, summary, date, timestamp, completed, highlights, tomorrow_plan |
| `daily-diary` | 2.0 | 每日日记 | 同 grouped-panels |
| `panel-report` | 2.0 | 诊断报告 | title, summary, timestamp, report_window, stats, major_findings, jobs |
| `diagnosis-report` | 2.0 | 诊断报告 | 同 panel-report |
| `distribution-report` | 1.0 | 分发报告 | 同 distribution-summary |

## 示例

### 创建通用报告

```bash
python3 scripts/scaffold_agent_task.py \
  --template-name weekly-summary \
  --template-description "周度总结" \
  --agent-id main \
  --job-name "weekly-summary-report" \
  --layout generic \
  --target-id oc_xxxxx \
  --channel topic \
  --cron "0 18 * * 5" \
  --header-template wathet
```

### 创建监控报告

```bash
python3 scripts/scaffold_agent_task.py \
  --template-name server-check \
  --template-description "服务器巡检" \
  --agent-id coding \
  --job-name "server-health-check" \
  --layout system-status \
  --target-id oc_xxxxx \
  --channel topic \
  --cron "0 */6 * * *" \
  --header-template red
```

### 创建私聊通知

```bash
python3 scripts/scaffold_agent_task.py \
  --template-name daily-reminder \
  --template-description "每日提醒" \
  --agent-id task \
  --job-name "daily-task-reminder" \
  --layout generic \
  --target-id ou_xxxxx \
  --target-type open_id \
  --channel direct \
  --cron "0 9 * * *"
```

## scaffold 生成的文件

| 文件 | 说明 |
|------|------|
| `runtime/feishu-templates.local.json` | 新增模板条目 |
| `runtime/jobs-spec.local.json` | 新增定时任务条目 |
| `runtime/payloads/{template-name}.example.json` | 示例 payload |

## 后续步骤

1. 检查并调整 `feishu-templates.local.json` 中生成的 blocks
2. 用 `send_message.py` 发送测试消息验证
3. 用 `sync_openclaw_jobs.py --apply` 同步到 OpenClaw
