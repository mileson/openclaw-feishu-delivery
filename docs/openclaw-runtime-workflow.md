# OpenClaw Runtime Workflow

这个文件描述的是“开源 repo 代码”和“本地私有运行时配置”如何协作。

相关文档：

- [`../README.md`](../README.md)
- [`template-contract.md`](template-contract.md)
- [`presentation-schema.md`](presentation-schema.md)

```ascii
GitHub repo
openclaw-feishu-delivery/
├─ src/ scripts/                 -> 可提交、可开源的真正逻辑
├─ examples/                     -> 公开参考模板
├─ runtime/                      -> 本地私有配置，不提交
│  ├─ feishu-templates.local.json
│  ├─ accounts.local.json
│  └─ jobs-spec.local.json
├─ state/                        -> 运行时状态，不提交
└─ logs/                         -> 审计日志，不提交
```

## 核心原则

- `src/` 与 `scripts/` 是唯一代码源，后续优化直接发 GitHub。
- `runtime/` 只放本地私有配置，不要提交群 ID、open_id、app_secret。
- OpenClaw 正式任务通过 `openclaw cron add/edit` 同步，不直接手改 `~/.openclaw/cron/jobs.json`。
- 若你的本地环境已有 onboarding automation / Skill，应该由它来调用本项目脚本，而不是在本仓库里再复制一套 onboarding 主流程。

## 典型流程

```ascii
1. 初始化 runtime
   -> python3 scripts/bootstrap_runtime.py

2. 编辑本地私有模板
   -> runtime/feishu-templates.local.json
   -> runtime/accounts.local.json
   -> runtime/jobs-spec.local.json

3. 预览 jobs 变更
   -> python3 scripts/sync_openclaw_jobs.py --spec-file runtime/jobs-spec.local.json

4. 应用 jobs 变更
   -> python3 scripts/sync_openclaw_jobs.py --spec-file runtime/jobs-spec.local.json --apply
```

## `jobs-spec.local.json` 的职责

- 声明要创建或更新哪些 OpenClaw cron jobs
- 用 `{{job_id}}` 占位，交给同步工具在实际 job id 分配后回填
- 统一把任务里的飞书发送入口指向 repo 自己的 `scripts/send_message.py`

## 为什么要保留 `jobs.json`

`~/.openclaw/cron/jobs.json` 是 OpenClaw Gateway 管理的官方任务库。

- 它负责：调度、启停、状态、历史关联
- 它不负责：飞书 route、固定话题、账号密钥

所以推荐拆层：

```ascii
OpenClaw jobs.json
  -> 什么时候跑
  -> 谁来跑
  -> job_id 是多少

runtime/feishu-templates.local.json
  -> 发到哪
  -> 是 direct / message / topic
  -> 固定话题标题
  -> thread_summary / @ 谁

runtime/accounts.local.json
  -> 每个 agent 用哪个飞书 app_id / app_secret
```
