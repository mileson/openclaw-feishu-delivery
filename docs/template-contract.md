# Template Contract

这个文档定义“任务侧”和“消息项目侧”的责任边界。

结论先说：

```ascii
任务 / agent / cron
  -> 只负责业务逻辑
  -> 只负责产出 template_name + payload

openclaw-feishu-delivery
  -> 负责模板结构
  -> 负责 route / provider / account / channel / thread
  -> 负责摘要 reply / 重试 / 审计
```

## 1. 任务侧应该提供什么

任务 prompt、业务脚本、采集脚本，最终只应该明确三件事：

1. 用哪个模板
2. 这个模板需要哪些业务字段
3. 成功/失败怎么判定

例如：

```ascii
daily-knowledge
  -> 模板名：daily-knowledge
  -> payload：title / summary / report_date / execution_steps / insights / ...
  -> 成功信号：send_message.py 返回 “✅ 消息发送成功”
```

## 2. 任务侧不应该再写什么

这些内容不应该继续出现在任务 prompt、业务脚本、子脚本里：

- 群 ID / open_id / union_id
- `--target-id`
- `--target-type`
- `--delivery-channel`
- `--thread-*`
- 哪个 bot account 发
- 固定话题标题
- 摘要 reply 结构
- 卡片 blocks / 折叠样式 / header 颜色

这些都应该交给模板配置解决。

## 3. 模板配置层负责什么

```ascii
runtime/feishu-templates.local.json
  -> template.required_fields
  -> route.transport.provider
  -> route.transport.account
  -> route.target
  -> route.delivery.channel
  -> route.thread.binding_key_template
  -> route.thread.title_template
  -> route.thread.summary_reply
  -> presentation.schema
  -> presentation.structure
  -> presentation.styles
  -> presentation.blocks
```

也就是说，任务只说“我要发 `daily-knowledge`”，真正落到哪个群、是不是 fixed topic、要不要自动补摘要、卡片长什么样，全部由模板配置决定。

对于 OpenClaw cron 场景，推荐再往前走一步：

```ascii
agent cron job
  -> 只产出模板 payload
  -> 短 payload：最终回复写入 OPENCLAW_TEMPLATE_PAYLOAD block
  -> 长 payload：先落盘到 JSON 文件，再只回传 OPENCLAW_TEMPLATE_PAYLOAD_FILE
  -> project wrapper 解析 run summary
  -> wrapper 调用 send_template_payload()
```

这样能避免 agent 在 prompt 里临时拼接 `send_message.py --data '{...}'` 并口头声称发送成功。

推荐约定：

```ascii
短内容任务
  -> OPENCLAW_TEMPLATE_PAYLOAD_START
  -> {...}
  -> OPENCLAW_TEMPLATE_PAYLOAD_END

长内容任务
  -> 先写入 /root/.openclaw/tmp/cron-payloads/<job-id>.json
  -> 最终只输出：
     OPENCLAW_TEMPLATE_PAYLOAD_FILE: /root/.openclaw/tmp/cron-payloads/<job-id>.json
```

长内容任务优先使用文件交付，因为 OpenClaw 的 cron summary 可能截断较长 JSON，导致 wrapper 无法读取完整 payload。

建议把这层要求写进 `runtime/cron-delivery.local.json`，而不是塞进飞书模板配置：

```json
{
  "job_id": "d588b00c-9add-45ce-9e17-cc62ba0e99b2",
  "template": "skill-hourly-report",
  "agent_id": "evolution",
  "payload_mode": "file",
  "payload_dir": "/root/.openclaw/tmp/cron-payloads"
}
```

原因：

```ascii
feishu template
  -> 定义“消息发到哪里、长什么样”

cron wrapper config
  -> 定义“任务怎么把 payload 交给 wrapper”
```

也就是说，`payload_mode=file` 是任务交付协议，不是飞书消息模板样式。

## 4. 标准发送方式

任务侧唯一推荐的结构化消息发送方式是：

```bash
python3 /root/.openclaw/projects/openclaw-feishu-delivery/scripts/send_message.py \
  --mode template \
  --job-id "{{job_id}}" \
  --jobs-file "/root/.openclaw/cron/jobs.json" \
  --templates-file "/root/.openclaw/projects/openclaw-feishu-delivery/runtime/feishu-templates.local.json" \
  --accounts-file "/root/.openclaw/projects/openclaw-feishu-delivery/runtime/accounts.local.json" \
  --agent-id "{agent_id}" \
  --template "{template_name}" \
  --data '{...}'
```

## 5. 推荐的 prompt 写法

```ascii
任务 prompt
  -> 先描述业务动作
  -> 再列出 payload 必填字段
  -> 最后给 wrapper 交付协议
```

推荐写法：

- 路由由模板配置决定，禁止手填 target / delivery / thread 参数
- 固定话题任务必须提供 `thread_summary`
- 长内容任务优先写 payload 文件，再输出 `OPENCLAW_TEMPLATE_PAYLOAD_FILE`
- 不要在 summary 里声称“已发送成功”；发送成功与否由 wrapper 审计决定

## 6. 不推荐的写法

下面这些都属于 legacy 写法，应该逐步移除：

- “必须读取旧的飞书消息规范文档”
- “飞书消息统一通过某个旧脚本发送”
- “这个任务固定发到某个 chat_id”
- “如果是 topic 就在 prompt 里手写 thread title”
- “在业务脚本内部拼 Feishu 卡片 JSON”

## 7. 一个健康的分层例子

```ascii
job prompt
  -> 只描述：AI 热点搜索 / Bitable 入库 / 需要的 payload

runtime template
  -> ai-hotspot
     -> provider = feishu
     -> account = blogger
     -> channel = topic
     -> binding_key = blogger:ai-hotspot
     -> title = 【AI 热点扫描】
     -> summary_reply = enabled
     -> presentation = items-report
```

这样做的好处：

- 模板变更不需要改 prompt
- 群路由调整不需要改脚本
- 样式升级不需要改 renderer
- 新 agent 只要接入 runtime account 就能复用统一发送方式
