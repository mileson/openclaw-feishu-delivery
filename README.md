# OpenClaw Feishu Cron Kit

> 一套面向新手的飞书消息发送机制示例项目，解决 3 个问题：模板化发送、固定话题持续回复、失败自动补发。

## 这是什么

如果你正在做下面这类事情，这个项目就是给你准备的：

- 让一个 Agent 或定时任务把结果发到飞书
- 希望同一类报告始终沉淀在**同一个话题**里，而不是每次新开一条消息
- 希望每次完整报告之后，再自动补一条**摘要 reply**
- 希望飞书临时失败时，不要等到下一小时或明天才恢复，而是自动补发

这个项目把这套机制拆成了一个独立、可开源、可复用的最小实现。

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
- 所有示例配置都已脱敏，可直接作为模板改造

## 适合谁

- 正在用 OpenClaw 或类似多 Agent 系统的人
- 想把 Python 脚本、cron、GitHub Actions 结果推送到飞书的人
- 想做“固定话题沉淀 + 自动摘要 + 自动重试”的人
- 不想一上来就接复杂框架、只想先跑通的人

## 项目结构

```ascii
openclaw-feishu-cron-kit
├─ src/openclaw_feishu_cron_kit/
│  ├─ core.py              # 核心逻辑：模板发送、固定话题、补发队列
│  ├─ renderer.py          # 卡片和摘要渲染
│  └─ storage.py           # JSON / JSONL 持久化
├─ scripts/
│  ├─ send_message.py      # 主 CLI 入口
│  └─ process_retry_queue.py
├─ examples/
│  ├─ feishu-templates.example.json
│  ├─ jobs.example.json
│  ├─ accounts.example.json
│  └─ payloads/
├─ state/                  # 本地运行时状态（默认不提交）
├─ logs/                   # 本地审计日志（默认不提交）
├─ .env.example
├─ pyproject.toml
└─ README.md
```

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

### 3. 一个目录用于保存状态和日志

默认就是项目内的：

- `state/`
- `logs/`

如果你要部署到服务器，可以用参数改掉。

## 快速开始

### 第一步：安装依赖

```bash
cd openclaw-feishu-cron-kit
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

- [accounts.example.json](/Users/mileson/Workspace/AI%20元宇宙/openclaw-feishu-cron-kit/examples/accounts.example.json)

### 第三步：改模板配置

打开：

- [feishu-templates.example.json](/Users/mileson/Workspace/AI%20元宇宙/openclaw-feishu-cron-kit/examples/feishu-templates.example.json)

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

### 第四步：准备 jobs 配置

打开：

- [jobs.example.json](/Users/mileson/Workspace/AI%20元宇宙/openclaw-feishu-cron-kit/examples/jobs.example.json)

你要让每个任务有一个稳定的 `job_id`。  
这个很重要，因为它会影响固定话题身份和补发记录。

```ascii
错误做法
  -> 每次随机 job_id
  -> 容易新开错误话题

正确做法
  -> 一个业务任务，对应一个稳定 job_id
```

### 第五步：准备 payload 数据

示例已经给你了：

- [ai-hotspot.example.json](/Users/mileson/Workspace/AI%20元宇宙/openclaw-feishu-cron-kit/examples/payloads/ai-hotspot.example.json)
- [daily-diary.example.json](/Users/mileson/Workspace/AI%20元宇宙/openclaw-feishu-cron-kit/examples/payloads/daily-diary.example.json)

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
*/5 * * * * cd /path/to/openclaw-feishu-cron-kit && /usr/bin/python3 scripts/process_retry_queue.py >> logs/retry-worker.log 2>&1
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
