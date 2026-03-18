# Migrate From Legacy OpenClaw Docs

这个文档用于说明旧版 `workspace/docs` 里的规范，应该如何收口到项目文档体系。

## 1. 旧体系的问题

旧体系的核心问题不是“文档太多”，而是规范源分裂：

```ascii
旧体系
├─ workspace/docs/feishu-message-standard.md
├─ workspace/docs/cron-task-template.md
├─ workspace/docs/agent-onboarding-*.md
├─ workspace/docs/shared-memory.md
└─ 各业务 prompt 自己再写一套飞书发送说明
```

最终结果是：

- 旧脚本路径持续传播
- route / topic / account 语义散落在 prompt
- 新增 agent 时继续复制旧规范
- 项目仓库已经升级，但认知层还停在旧体系

## 2. 新体系的规范源

```ascii
openclaw-feishu-delivery/
├─ README.md
├─ docs/openclaw-runtime-workflow.md
├─ docs/template-contract.md
└─ docs/presentation-schema.md
```

## 3. 推荐映射关系

### 旧文档 -> 新文档

- `workspace/docs/feishu-message-standard.md`
  - 收口到 `README.md` + `docs/template-contract.md` + `docs/presentation-schema.md`
- `workspace/docs/cron-task-template.md`
  - 收口到 `docs/template-contract.md` + `examples/jobs-spec.example.json`
- `workspace/docs/agent-onboarding-checklist.md`
  - 收口到本地 onboarding automation / Skill，不再在项目 docs 中维护第二入口
- `workspace/docs/agent-onboarding-feishu-rules-enforcement.md`
  - 收口到本地 onboarding automation / Skill，不再在项目 docs 中维护第二入口
- `workspace/docs/feishu-rules-propagation.md`
  - 退场，不再单独维护
- `workspace/docs/shared-memory.md`
  - 如需保留，只保留“项目文档入口”，不再维护旧脚本铁律

## 4. 旧业务 prompt 怎么迁

旧 prompt 常见写法：

- 先要求读取旧规范文档
- 再要求调用旧发送脚本
- 再在 prompt 里讲 fixed topic / 群 ID / summary reply

新 prompt 推荐写法：

```ascii
业务步骤
  -> payload contract
  -> send_message.py 骨架
  -> 成功/失败标准
```

route / account / thread / presentation 统一交给模板配置。

## 5. 备份文件怎么处理

所有 `*.bak*`、历史时间点修复稿、旧 prompt 快照，都不建议继续重写。

推荐处理：

- 保留备份
- 不再作为规范源
- 如需说明，只在文档顶部写“历史归档，不再维护”

## 6. 收口完成后的判断标准

```ascii
达标标准
├─ live jobs 不再直接引用旧脚本
├─ onboarding Skill 不再传播旧脚本
├─ workspace/docs 不再自称“唯一规范源”
├─ 新 agent 默认读项目文档
└─ 新任务默认用 scaffold_agent_task.py 建立模板和 jobs-spec
```
