[**简体中文**](README.md) | [English](README.en.md)

# OpenClaw 飞书消息发送

> 让 OpenClaw 把日报、巡检、内容发布和监控结果稳定发到飞书固定话题的消息投递项目。

## 这是什么

如果你正在做下面这类事情，这个项目就是给你准备的：

- 让一个 Agent 或定时任务把结果发到飞书
- 希望同一类报告始终沉淀在**同一个话题**里，而不是每次新开一条消息
- 希望每次完整报告之后，再自动补一条**摘要 reply**
- 希望飞书临时失败时，不要等到下一小时或明天才恢复，而是自动补发

这个仓库不是“为了开源而发明一套新的通用框架”，而是把真实生产里已经跑顺的飞书投递主链路整理出来，方便你复用到自己的 OpenClaw、多 Agent 调度系统或 cron 环境里。

```ascii
你会得到的能力
────────────────────────────────
定时任务 / Agent
  -> 发送模板消息
  -> 自动落到固定话题
  -> 自动补一条摘要 reply
  -> 失败时自动进入补发队列
  -> 5 分钟后第 2 次补发
  -> 30 分钟后第 3 次补发
  -> 第 3 次还失败才标记最终失败
```

## 功能亮点

- 支持 `template` / `text` / `retry-pending` 三种模式
- 支持飞书群普通消息、群话题消息、私聊消息
- 支持固定话题绑定 `binding_key_template`
- 支持同话题自动摘要 reply
- 支持补发队列与补发审计
- 支持 `jobs.json` 校验，避免错误 `job_id` 新开错误话题
- 多 Agent 多账号可独立配置，适合实际生产中的多机器人模式
- 所有示例配置都已脱敏，但模板名称和业务场景保持生产实际语义

## 这些内容来自真实生产场景

这个仓库里的模板名称和任务类型，不是为了开源特意虚构的，而是来自真实生产里长期使用的 Agent 流水线节点，例如：

```ascii
内容侧（blogger）
  -> AI 热点扫描
  -> 深度选题研究
  -> 周度即刻选题计划
  -> 即刻 - 自动化内容创作
  -> 即刻评论回复监控
  -> Twitter/X 社媒监控

总管侧（main）
  -> 每日日记汇总
  -> 每日知识整理

工程侧（engineer）
  -> 系统状态巡检

进化侧（evolution）
  -> 高质量 Skill 挖掘
  -> Skill 试用评估报告
  -> Skill 智能分发
```

这里做了两层取舍：

- 保留真实业务节点名称、固定话题思路、补发机制和多 Agent 路由方式
- 去掉真实群 ID、open_id、App 凭证、生产路径和内部耦合实现

## 适合谁

- 正在用 OpenClaw 或类似多 Agent 系统的人
- 想把 Python 脚本、cron、GitHub Actions 结果推送到飞书的人
- 想做“固定话题沉淀 + 自动摘要 + 自动重试”的人
- 不想一上来就接复杂框架、只想先跑通的人

## 它解决的不是“发一条消息”，而是“稳定投递一类业务结果”

```ascii
常见业务结果
────────────────────────────────
内容侧
  -> AI 热点扫描
  -> 深度选题研究
  -> 即刻自动化内容创作
  -> Twitter/X 社媒监控

工程侧
  -> 系统状态巡检

进化侧
  -> Skill 挖掘
  -> Skill 试用评估
  -> Skill 智能分发

总管侧
  -> 每日日记汇总
  -> 每日知识整理
```

也就是说，这个仓库更像一套“飞书结果投递底座”，而不是一个单独的消息脚本。

## 项目结构

```ascii
openclaw-feishu-delivery
├─ src/openclaw_feishu_cron_kit/
│  ├─ core.py              # 核心逻辑：模板发送、固定话题、补发队列
│  ├─ renderer.py          # 卡片和摘要渲染
│  └─ storage.py           # JSON / JSONL 持久化
├─ scripts/
│  ├─ send_message.py      # 主 CLI 入口
│  └─ process_retry_queue.py
│  ├─ materialize_template_presentations.py
│  └─ scaffold_agent_task.py
├─ examples/
│  ├─ feishu-templates.example.json
│  ├─ jobs.example.json
│  ├─ accounts.example.json
│  └─ payloads/            # 生产场景脱敏样例
├─ state/                  # 本地运行时状态（默认不提交）
├─ logs/                   # 本地审计日志（默认不提交）
├─ .env.example
├─ pyproject.toml
└─ README.md
```

## 配置优先的运行模型

这套工具现在的运行期原则很简单：

```ascii
模板配置
  -> route.transport.provider   # feishu / telegram / discord
  -> route.delivery.channel     # direct / message / topic
  -> presentation.schema        # 1.0 / 2.0
  -> presentation.structure     # generic / collapsible-list / grouped-panels / panel-report
  -> presentation.styles        # 面板样式、颜色、图标
  -> presentation.blocks        # 卡片怎么拼
  -> required_fields            # payload 最低字段要求

脚本
  -> 读取模板配置
  -> 校验 payload
  -> 按 blocks 拼卡片
  -> 按 provider 分发
```

也就是说，脚本本身不再承担“这个模板长什么样”的业务语义。  
运行期真正决定消息内容的，是模板配置中的 `presentation.schema + structure + styles + blocks`。

推荐优先按“功能型结构族”选模板，而不是先按业务场景命名渲染器：

```ascii
结构族
├─ generic
│  └─ 普通线性报告，适合状态、列表、简报
├─ collapsible-list
│  └─ 单卡片 + 多个折叠列表，适合知识整理、日报
├─ grouped-panels
│  └─ 按记录动态生成多个 panel，适合 agent 分组推荐
└─ panel-report
   └─ 摘要 + 发现 + 任务详情 panel，适合诊断/巡检
```

推荐的模板结构如下：

```json
{
  "templates": {
    "daily-knowledge": {
      "description": "每日知识整理",
      "header_template": "blue",
      "required_fields": ["title", "summary", "report_date", "organized_at", "execution_steps", "timestamp", "thread_summary"],
      "presentation": {
        "schema": "2.0",
        "structure": "collapsible-list",
        "header_title_template": "📚 每日知识整理 · {report_date}",
        "styles": {
          "panels": {
            "default": {
              "title_color": "#333333",
              "header_background_color": "grey",
              "border_color": "grey"
            }
          }
        },
        "blocks": [
          {"type": "plain_text", "template": "{summary}"},
          {"type": "plain_text", "template": "{report_date} | {timestamp}"},
          {"type": "divider"},
          {
            "type": "collapsible_panel",
            "title": "✅ 执行步骤（{execution_steps_count}）",
            "expanded": true,
            "blocks": [
              {
                "type": "record_list",
                "path": "execution_steps",
                "title": "",
                "show_title": false,
                "title_template": "<font color='#1890FF'>• **{name}**</font>",
                "lines": ["文件：`{file}`", "{detail}"]
              }
            ]
          },
          {
            "type": "collapsible_panel",
            "title": "💡 关键洞察（{insights_count}）",
            "expanded": false,
            "blocks": [
              {
                "type": "list",
                "path": "insights",
                "title": "",
                "show_title": false,
                "empty_text": "本轮没有新增洞察。"
              }
            ]
          }
        ]
      },
      "route": {
        "transport": {"provider": "feishu", "account": "main"},
        "target": {"id": "oc_xxx", "type": "chat_id"},
        "delivery": {"channel": "topic"},
        "policy": {"lock_target": true, "lock_delivery": true},
        "thread": {
          "enabled": true,
          "binding_key_template": "main:daily-knowledge",
          "title_template": "【每日知识整理】",
          "summary_reply": {"enabled": true, "required": true, "channel": "text"}
        }
      }
    }
  }
}
```

## 旧模板迁移为配置 blocks

如果你手里还有旧的 `renderer` 模板，不需要再把渲染逻辑写回 Python。  
直接把旧模板一次性 materialize 成 `presentation.schema + structure + styles + blocks` 即可：

```bash
python3 scripts/materialize_template_presentations.py \
  --templates-file runtime/feishu-templates.local.json \
  --write \
  --drop-renderer
```

这个脚本只负责做一次迁移：

- 根据已知模板类型生成标准结构族配置
- 把旧的 `renderer` 字段移除
- 让运行期只依赖配置，不再依赖模板名对应的 Python 逻辑

## 工作原理

```ascii
发送成功路径
────────────────────────────────
cron / agent
  -> scripts/send_message.py --mode template
  -> 读取模板配置
  -> 校验 job_id
  -> 解析 route + thread
  -> 发完整卡片
  -> 如果是 topic
       -> 自动补一条摘要 reply


发送失败路径
────────────────────────────────
首次发送
  -> 可重试错误
       -> 写入 state/feishu-retry-queue.json
       -> 5 分钟后补第 2 次
       -> 再失败 30 分钟后补第 3 次
       -> 再失败则标记最终失败

不可重试错误
  -> 直接失败
  -> 不进入补发队列
```

## 一键新增 Agent 任务

后续新增一个 Agent 的飞书定时任务，不建议手改多份 JSON。  
直接用脚手架生成模板、任务定义和 payload 示例：

```bash
python3 scripts/scaffold_agent_task.py \
  --runtime-dir runtime \
  --repo-path /root/.openclaw/projects/openclaw-feishu-delivery \
  --template-name weekly-ops-report \
  --template-description "每周运维汇总" \
  --agent-id engineer \
  --job-name "每周运维汇总" \
  --job-description "每周汇总核心运维状态并发送固定话题报告" \
  --layout panel-report \
  --channel topic \
  --transport-provider feishu \
  --transport-account engineer \
  --target-id oc_xxx \
  --binding-key engineer:weekly-ops-report \
  --thread-title "【每周运维汇总】" \
  --cron "0 10 * * 1"
```

脚手架会生成：

- `runtime/feishu-templates.local.json` 中的新模板
- `runtime/jobs-spec.local.json` 中的新任务定义
- `runtime/payloads/<template>.example.json` 示例 payload

推荐优先使用这些结构族名称：

- `generic`
- `collapsible-list`
- `grouped-panels`
- `panel-report`
- `distribution-summary`

旧名字如 `knowledge-digest`、`diagnosis-report`、`daily-diary` 仍保留为兼容别名。

然后再同步到 OpenClaw：

```bash
python3 scripts/sync_openclaw_jobs.py --spec-file runtime/jobs-spec.local.json
```

## 如果希望让“小龙虾 OpenClaw”安装这套工具，提示词如下

```text
请将下面这段提示词发送给你的小龙虾 OpenClaw，它将自动学习这套工具、完成安装部署、按当前系统里的 agent 设计模板与配置，并在验证通过后再向你汇报结果。

请阅读 https://github.com/mileson/openclaw-feishu-delivery ，重点阅读 README、examples/feishu-templates.example.json、examples/jobs.example.json、examples/accounts.example.json 以及 examples/payloads/ 下的示例。先总结这套飞书固定话题、模板发送和失败补发机制，重点说明：模板如何决定 route、job_id 与 binding_key 如何决定固定话题、完整卡片与摘要 reply 如何分层、失败补发如何工作、以及多 agent 下为什么不能直接复用同一个 open_id。

然后请检查当前 OpenClaw 系统里一共有多少个 agent，它们分别是谁、各自负责什么业务、哪些 agent 需要接入这套飞书投递底座。基于当前实际 agent 情况，先生成一份按 agent 维度划分的接线草案，说明每个 agent 适合使用哪些模板、发到哪个群、是否固定话题、话题标题是什么、摘要是否需要 @ 人、是否启用失败补发。

接着把 openclaw-feishu-delivery 安装到当前 OpenClaw 服务器，要求 clone 到 /root/.openclaw/vendor/openclaw-feishu-delivery，创建虚拟环境并安装依赖，从 examples 复制出 config/feishu-templates.json、config/jobs.json、config/accounts.json，但不要覆盖现有生产配置文件，先生成候选配置。然后基于当前系统中的 agent 和业务任务，为每个需要接入的 agent 生成对应的 templates / jobs / accounts 映射草案与差异清单。

完成接线草案后，请尝试做发送验证：至少抽查 1 条定时任务链路和 1 条日常对话消息链路，验证是否能正确发到固定话题、是否会自动补摘要 reply、失败补发队列是否可运行、@ 人是否在当前 agent 的 open_id 作用域下生效。如果发现问题，请按“配置错误 / job_id 错误 / open_id 作用域错误 / 补发未接入”分类输出，并给我一份可执行的修复建议。

整个过程中请先输出理解总结、当前 agent 盘点结果、安装结果、差异清单、待确认配置表和验证结果；不要直接覆盖旧配置，也不要直接启用生产定时任务。只有当验证通过后，再向我汇报最终可执行方案。
```

## 运行前你要准备什么

### 1. Python 3.10+

推荐先确认版本：

```bash
python3 --version
```

### 2. 一个可用的飞书机器人

你至少需要：

- `app_id`
- `app_secret`
- 一个要发消息的目标 `chat_id`
- 如果你想在摘要里 `@某人`，还需要这个人的 `open_id`

### 2.1 如果你是多 Agent 模式

这套机制非常适合多 Agent 多机器人生产环境。

```ascii
推荐结构
────────────────────────────────
blogger agent
  -> blogger 飞书应用
  -> blogger 自己的 chat_id / open_id 作用域

main agent
  -> main 飞书应用
  -> main 自己的 chat_id / open_id 作用域

engineer agent
  -> engineer 飞书应用

evolution agent
  -> evolution 飞书应用
```

要注意一个很容易踩坑的事实：

```ascii
同一个接收人
  在不同飞书应用下
    -> open_id 可能不同
```

也就是说，如果你在 `blogger` 模板里能正确 `@超级峰`，不代表在 `evolution` 模板里也能直接复用同一个 `open_id`。

推荐做法：

- 每个 agent 对应自己的飞书应用账号
- 每个模板在自己的 agent 作用域下单独配置 `mention_open_ids`
- 不要跨 agent 复用同一个 `open_id` 占位值

### 3. 一个目录用于保存状态和日志

默认就是项目内的：

- `state/`
- `logs/`

如果你要部署到服务器，可以用参数改掉。

## 快速开始

### 第一步：安装依赖

```bash
cd openclaw-feishu-delivery
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 第二步：配置飞书凭证

最简单的方式是环境变量：

```bash
cp .env.example .env
```

然后把 `.env` 改成真实值：

```env
FEISHU_APP_ID=your_real_app_id
FEISHU_APP_SECRET=your_real_app_secret
```

如果你不想用环境变量，也可以参考：

- [accounts.example.json](examples/accounts.example.json)

### 第三步：改模板配置

打开：

- [feishu-templates.example.json](examples/feishu-templates.example.json)

你至少要改 3 个字段：

```json
{
  "target": {
    "id": "oc_your_chat_id_here",
    "type": "chat_id"
  },
  "thread": {
    "binding_key_template": "blogger:ai-hotspot",
    "title_template": "【AI 热点扫描】",
    "summary_reply": {
      "mention_open_ids": ["ou_your_open_id_here"]
    }
  }
}
```

解释一下：

- `target.id`：你要发到哪个飞书群
- `binding_key_template`：固定话题身份
- `title_template`：第一次创建话题时的话题标题
- `mention_open_ids`：摘要 reply 里要 @ 谁

如果你是多 Agent 模式，建议直接按 agent 分组配置模板，而不是做一个所有人共用的大杂烩模板集。

```ascii
推荐做法
────────────────────────────────
blogger
  -> ai-hotspot
  -> topic-research-report
  -> jike-publish-report

main
  -> daily-diary
  -> daily-knowledge

engineer
  -> system-status

evolution
  -> skill-discovery-report
  -> skill-trial-report
  -> skill-distribution
```

### 第四步：准备 jobs 配置

打开：

- [jobs.example.json](examples/jobs.example.json)

你要让每个任务有一个稳定的 `job_id`。  
这个很重要，因为它会影响固定话题身份和补发记录。

```ascii
错误做法
  -> 每次随机 job_id
  -> 容易新开错误话题

正确做法
  -> 一个业务任务，对应一个稳定 job_id
```

当前示例 `jobs.example.json` 里，已经直接放了贴近生产的任务名，例如：

- `AI 热点扫描（每2小时）`
- `深度选题研究（每天）`
- `即刻自动化内容创作（每小时）`
- `Twitter/X 社媒监控（每小时）`
- `每日日记汇总`
- `系统状态巡检（每小时）`
- `进化官每小时 Skill 搜索测试`

### 第五步：准备 payload 数据

示例已经给你了：

- [ai-hotspot.example.json](examples/payloads/ai-hotspot.example.json)
- [daily-diary.example.json](examples/payloads/daily-diary.example.json)
- [twitter-monitor.example.json](examples/payloads/twitter-monitor.example.json)
- [system-status.example.json](examples/payloads/system-status.example.json)
- [skill-trial.example.json](examples/payloads/skill-trial.example.json)
- [jike-publish.example.json](examples/payloads/jike-publish.example.json)

你最需要关心的是 `thread_summary`：

```json
"thread_summary": {
  "notice": "AI 热点扫描已完成",
  "bullets": [
    "新增高分选题：2 个",
    "最高优先级：OpenAI 新模型迭代",
    "详情见上一条完整卡片"
  ],
  "footer": "详情见上一条完整卡片。",
  "mention_open_ids": ["ou_your_open_id_here"]
}
```

## 第一次发送一条模板消息

推荐直接先发一条测试消息：

```bash
python3 scripts/send_message.py \
  --mode template \
  --agent-id blogger \
  --job-id blogger-ai-hotspot-hourly \
  --jobs-file examples/jobs.example.json \
  --templates-file examples/feishu-templates.example.json \
  --template ai-hotspot \
  --data "$(cat examples/payloads/ai-hotspot.example.json)"
```

如果发送成功，你会看到类似输出：

```ascii
📨 路由解析：channel=topic target=chat_id:oc_xxx
🧵 固定话题：key=blogger:ai-hotspot title=【AI 热点扫描】
✅ 群话题消息发送成功
✅ 群话题摘要回复发送成功
```

## 如何让补发机制生效

你有两种跑法。

### 方式 A：手动处理

```bash
python3 scripts/send_message.py --mode retry-pending
```

或者：

```bash
python3 scripts/process_retry_queue.py
```

### 方式 B：配合 cron

推荐每 5 分钟扫一次：

```cron
*/5 * * * * cd /path/to/openclaw-feishu-delivery && /usr/bin/python3 scripts/process_retry_queue.py >> logs/retry-worker.log 2>&1
```

推荐把补发 worker 当成宿主机本地任务，不要注册成某个 agent 的定时任务。

```ascii
推荐
────────────────────────────────
宿主机 cron / systemd timer
  -> process_retry_queue.py
  -> 只消费 feishu-retry-queue.json
  -> 不占用 main / blogger / product 等 agent 并发

不推荐
────────────────────────────────
OpenClaw jobs.json
  -> agentId = main
  -> payload.kind = systemEvent
  -> 在控制台里看起来像总管任务
  -> 容易和 agent 运行槽位混淆
```

## 固定话题是怎么工作的

```ascii
第一次发送
────────────────────────────────
模板 ai-hotspot
  -> route.delivery.channel = topic
  -> binding_key_template = blogger:ai-hotspot
  -> 创建 root message
  -> 保存 root_message_id 到 state/feishu-thread-bindings.json

后续发送
────────────────────────────────
同一个 binding_key
  -> 找到 root_message_id
  -> reply 到同一个话题
  -> 不再新开话题
```

## 生产环境里推荐怎么组织多 Agent

如果你准备把这套东西放回真实生产环境，建议按下面的结构组织：

```ascii
生产推荐组织方式
────────────────────────────────
accounts.example.json
  -> 管理不同 agent 的 app_id / app_secret

feishu-templates.example.json
  -> 管理不同 agent 的模板、群路由、固定话题名、@人配置

jobs.example.json
  -> 管理每条定时任务的稳定 job_id 和 schedule

payloads/
  -> 放各个业务模板对应的数据结构示例
```

不要这样做：

```ascii
不推荐
────────────────────────────────
1. agent 自己手写 target-id
2. agent 自己手写 delivery-channel
3. agent 自己自由拼 thread-title
4. 不同 agent 共用同一个 open_id 配置
5. job_id 每次动态生成
```

推荐这样做：

```ascii
推荐
────────────────────────────────
1. 模板决定发到哪
2. job_id 决定这是哪条固定任务
3. binding_key_template 决定固定话题身份
4. 各 agent 维护自己的 open_id 作用域
5. payload 只负责传业务数据
```

## 哪些错误会自动补发

会补发：

- 网络超时
- 429
- 5xx
- 网关错误
- 连接被拒绝 / 代理故障 / 临时网络抖动

不会补发：

- `job_id` 不存在
- 模板缺字段
- `chat_id` / `open_id` 配错
- `delivery.channel` 非法
- 明显的参数错误

## 运行后会生成哪些文件

```ascii
state/
  feishu-thread-bindings.json   # 固定话题绑定
  feishu-retry-queue.json       # 补发队列

logs/
  feishu-send-audit.jsonl       # 发送审计
  feishu-thread-audit.jsonl     # 线程审计
  feishu-retry-audit.jsonl      # 补发审计
```

## 常见问题

### 1. 为什么我发消息后新开了一个话题？

优先检查这几个点：

- `job_id` 是否稳定
- `binding_key_template` 是否变了
- 你是不是手工加了 `--thread-key` / `--thread-title`
- 线程记录文件是不是被删了

### 2. 为什么摘要里没有 @ 到人？

先检查：

- `mention_open_ids` 写的是不是目标用户的 `open_id`
- 你发的是不是 `summary_reply`
- 对方是不是在群里

### 3. 为什么失败后没有自动重发？

先检查：

- 有没有运行 `retry-pending`
- `state/feishu-retry-queue.json` 里有没有 pending 记录
- 这次错误是不是不可重试错误

## 安全说明

这个仓库已经做了脱敏处理：

- 不包含真实 `chat_id`
- 不包含真实 `open_id`
- 不包含真实 `app_secret`
- 不包含任何生产环境路径

但仓库中保留了真实生产里的任务语义和模板命名方式，目的是让你能直接理解：

- 哪些任务适合固定话题
- 哪些任务适合摘要 reply
- 多 Agent 模式下配置应该放在哪一层

你在使用时，请自己替换为真实值，并确保：

- `.env` 不要提交
- `state/` 和 `logs/` 不要提交
- 不要把真实群 ID 和用户 ID 写进 README

## 适合二次开发的方向

- 增加更多模板 renderer
- 接入更多消息类型
- 第三次失败后自动发运维告警
- 增加 Web UI
- 增加失败队列清理工具

## License

MIT
