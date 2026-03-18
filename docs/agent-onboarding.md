# Agent Onboarding

这个文档描述一个新 agent 如何接入 `openclaw-feishu-delivery`。

```ascii
新 agent 入职
  -> 先接 OpenClaw agent/binding/account
  -> 再接 delivery runtime account
  -> 再生成角色文档
  -> 最后为首个任务 scaffold 模板与 job spec
```

## 1. 入职分两层

### OpenClaw 层

负责：

- `openclaw.json.agents.list`
- `openclaw.json.bindings`
- `openclaw.json.channels.feishu.accounts`
- `userIdentities`
- workspace / agentDir / sessions

### Delivery 项目层

负责：

- `runtime/accounts.local.json`
- `runtime/feishu-templates.local.json`
- `runtime/jobs-spec.local.json`

两层缺一不可。

## 2. 新 agent 至少要完成什么

```ascii
OpenClaw 配置
  -> agent 已注册
  -> Feishu binding 已建立
  -> Feishu account 已存在
  -> open_id identity 已可用

Delivery runtime
  -> accounts.local.json 已有该 agent account
  -> MEMORY.md 已写明项目化消息铁律
  -> 若已有首个任务，模板与 jobs-spec 已建立
```

## 3. runtime account 的职责

`runtime/accounts.local.json` 只负责“这个 agent 在消息项目里用哪个 app_id / app_secret”。

它不负责：

- route
- topic
- template blocks
- job 调度

也就是说：

```ascii
新 agent 入职
  -> 先同步 delivery account
  -> 之后这个 agent 才能被模板 route.transport.account 正常引用
```

## 3.5 MEMORY 注入怎么做

`MEMORY.md` 的项目化消息铁律不建议手工复制。推荐用脚本维护受管区块：

```ascii
项目级
  -> sync_workspace_memory_rules.py
  -> 只读取 openclaw.json 里的真实 agent workspaces

单 agent 入职
  -> agent-onboarding/scripts/inject_agent_memory_rules.py
  -> 只改当前 agent 的 MEMORY.md
```

项目级批量同步：

```bash
python3 /root/.openclaw/projects/openclaw-feishu-delivery/scripts/sync_workspace_memory_rules.py
python3 /root/.openclaw/projects/openclaw-feishu-delivery/scripts/sync_workspace_memory_rules.py --apply
```

要求：

- 已有区块时执行“替换”，不重复追加
- 旧的手写“飞书消息项目铁律”会被归一化成受管区块
- 规则里的绝对路径始终以项目真实位置推导

## 4. 首个任务怎么建立

如果 onboarding 同时要接入首个定时任务或固定话题模板，不要手写配置，优先使用项目脚手架：

```bash
python3 /root/.openclaw/projects/openclaw-feishu-delivery/scripts/scaffold_agent_task.py \
  --runtime-dir /root/.openclaw/projects/openclaw-feishu-delivery/runtime \
  --repo-path /root/.openclaw/projects/openclaw-feishu-delivery \
  --template-name "example-template" \
  --template-description "示例任务汇报" \
  --agent-id "example" \
  --job-name "示例任务" \
  --layout grouped-panels \
  --channel topic \
  --target-id "oc_xxx" \
  --target-type chat_id \
  --cron "0 9 * * *"
```

脚手架会生成：

- `runtime/feishu-templates.local.json` 新模板
- `runtime/jobs-spec.local.json` 新任务
- `runtime/payloads/*.example.json` 示例 payload

## 5. 任务 prompt 的推荐写法

任务 prompt 不再负责讲 route / topic / thread。

推荐只写：

- 业务动作
- payload 必填字段
- `send_message.py` 调用骨架
- 成功/失败信号

具体规则见：

- [`template-contract.md`](template-contract.md)
- [`openclaw-runtime-workflow.md`](openclaw-runtime-workflow.md)

## 6. onboarding Skill 应该做什么

如果你用 `agent-onboarding` Skill，新 agent 入职后的标准结果应该是：

1. OpenClaw 配置已 upsert
2. delivery runtime account 已 upsert
3. `IDENTITY.md / USER.md / MEMORY.md / AGENTS.md / TASK_POLICY.md` 已生成
4. `MEMORY.md` 已通过注入脚本写入项目化消息铁律
5. 如果已经知道首个任务，就继续调用项目脚手架生成模板和 job spec

## 7. onboarding Skill 不应该做什么

- 不应该继续传播旧的 `send_feishu_message.py`
- 不应该再让 `workspace/docs/feishu-message-standard.md` 充当唯一规范源
- 不应该在 Skill 内部再维护一套独立模板规范
- 不应该让新 agent 的 prompt 手填 `target / delivery / thread`
