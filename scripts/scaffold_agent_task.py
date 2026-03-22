#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from openclaw_feishu_cron_kit.presentation_presets import get_scaffold_layout, load_scaffold_layouts

SCAFFOLD_LAYOUTS = load_scaffold_layouts()


LAYOUT_REQUIRED_FIELDS: dict[str, list[str]] = {
    "generic": ["title", "summary", "sections", "timestamp"],
    "collapsible-list": [
        "title",
        "summary",
        "report_date",
        "organized_at",
        "execution_steps",
        "completed_tasks",
        "new_topics",
        "insights",
        "lessons",
        "timestamp",
    ],
    "grouped-panels": ["title", "summary", "date", "timestamp", "completed", "highlights", "tomorrow_plan"],
    "panel-report": ["title", "summary", "timestamp", "report_window", "stats", "major_findings", "jobs"],
    "distribution-summary": ["title", "timestamp", "skill_name", "source", "target_agent", "match_score"],
    "items-report": ["title", "count", "items", "timestamp"],
    "sections-report": ["title", "summary", "sections", "timestamp"],
    "system-status": ["title", "timestamp", "overall_status", "health_score"],
    "knowledge-digest": [
        "title",
        "summary",
        "report_date",
        "organized_at",
        "execution_steps",
        "completed_tasks",
        "new_topics",
        "insights",
        "lessons",
        "timestamp",
    ],
    "daily-diary": ["title", "summary", "date", "timestamp", "completed", "highlights", "tomorrow_plan"],
    "diagnosis-report": ["title", "summary", "timestamp", "report_window", "stats", "major_findings", "jobs"],
    "distribution-report": ["title", "timestamp", "skill_name", "source", "target_agent", "match_score"],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scaffold a new OpenClaw Feishu task into runtime config")
    parser.add_argument("--runtime-dir", default=str(ROOT / "runtime"))
    parser.add_argument("--template-name", required=True)
    parser.add_argument("--template-description", required=True)
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--job-name", required=True)
    parser.add_argument("--job-description", default="")
    parser.add_argument("--layout", required=True, choices=sorted(SCAFFOLD_LAYOUTS.keys()))
    parser.add_argument("--header-template", default="blue")
    parser.add_argument("--channel", default="topic", choices=["direct", "message", "topic"])
    parser.add_argument("--transport-provider", default="feishu")
    parser.add_argument("--transport-account")
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--target-type", default="chat_id")
    parser.add_argument("--binding-key")
    parser.add_argument("--thread-title")
    parser.add_argument("--mention-open-id", action="append", default=[])
    parser.add_argument("--schedule-kind", default="cron", choices=["cron", "every"])
    parser.add_argument("--cron")
    parser.add_argument("--tz", default="Asia/Shanghai")
    parser.add_argument("--every")
    parser.add_argument("--message")
    parser.add_argument("--repo-path", default=str(ROOT))
    parser.add_argument("--disabled", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def load_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return json.loads(json.dumps(default))
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_schedule(args: argparse.Namespace) -> dict:
    if args.schedule_kind == "cron":
        if not args.cron:
            raise ValueError("--schedule-kind cron 时必须提供 --cron")
        return {"kind": "cron", "expr": args.cron, "tz": args.tz}
    if not args.every:
        raise ValueError("--schedule-kind every 时必须提供 --every")
    return {"kind": "every", "every": args.every}


def build_route(args: argparse.Namespace) -> dict:
    route: dict[str, object] = {
        "transport": {
            "provider": args.transport_provider,
            "account": args.transport_account or args.agent_id,
        },
        "target": {"id": args.target_id, "type": args.target_type},
        "delivery": {"channel": args.channel},
        "policy": {"lock_target": True, "lock_delivery": True},
    }
    if args.channel == "topic":
        route["thread"] = {
            "enabled": True,
            "binding_key_template": args.binding_key or f"{args.agent_id}:{args.template_name}",
            "title_template": args.thread_title or f"【{args.template_description}】",
            "recreate_on_root_missing": True,
            "summary_reply": {
                "enabled": True,
                "required": True,
                "channel": "text",
                "mention_open_ids": args.mention_open_id,
            },
        }
    return route


def build_message(args: argparse.Namespace) -> str:
    if args.message:
        return args.message
    summary_hint = ""
    if args.channel == "topic":
        summary_hint = "\n- 固定话题任务必须提供 `thread_summary.notice + thread_summary.bullets`"
    return f"""请执行任务：{args.job_name}

1. 完成对应业务逻辑。
2. 组装 `{args.template_name}` 模板 payload。
3. 必须直接调用 repo 脚本发送飞书：

```bash
python3 {args.repo_path}/scripts/send_message.py \\
  --mode template \\
  --job-id "{{{{job_id}}}}" \\
  --jobs-file "/root/.openclaw/cron/jobs.json" \\
  --templates-file "{args.repo_path}/runtime/feishu-templates.local.json" \\
  --accounts-file "{args.repo_path}/runtime/accounts.local.json" \\
  --agent-id {args.agent_id} \\
  --template "{args.template_name}" \\
  --data '{{...}}'
```

要求：
- 路由由模板配置决定，禁止手填 `--target-id / --target-type / --delivery-channel / --thread-*`{summary_hint}
- 最终输出必须包含 send_message.py 原始输出中的「✅ 消息发送成功」"""


def build_template_config(args: argparse.Namespace) -> dict:
    required_fields = list(LAYOUT_REQUIRED_FIELDS[args.layout])
    if args.channel == "topic" and "thread_summary" not in required_fields:
        required_fields.append("thread_summary")
    return {
        "description": args.template_description,
        "header_template": args.header_template,
        "required_fields": required_fields,
        "presentation": get_scaffold_layout(args.layout),
        "route": build_route(args),
    }


def build_job_spec(args: argparse.Namespace) -> dict:
    return {
        "match": {"name": args.job_name},
        "name": args.job_name,
        "description": args.job_description or args.template_description,
        "enabled": not args.disabled,
        "agent": args.agent_id,
        "schedule": build_schedule(args),
        "payload": {
            "kind": "agentTurn",
            "message": build_message(args),
        },
    }


def build_example_payload(args: argparse.Namespace) -> dict:
    base: dict[str, object] = {
        "title": args.template_description,
        "summary": "请将这里替换为任务完成摘要。",
        "timestamp": "2026-03-18 09:00",
    }
    if args.layout == "items-report":
        base.update(
            {
                "count": 2,
                "items": [
                    {"emoji": "🧩", "title": "示例条目 1", "score": "SCORE 22/25", "description": "补充说明", "platform": "即刻"},
                    {"emoji": "📌", "title": "示例条目 2", "score": "SCORE 20/25", "description": "补充说明", "platform": "飞书"},
                ],
            }
        )
    elif args.layout in {"generic", "sections-report"}:
        base.update({"sections": [{"title": "核心内容", "lines": ["第一条", "第二条"]}]})
    elif args.layout == "system-status":
        base.update(
            {
                "overall_status": "healthy",
                "health_score": 96,
                "host": {"disk": {"used_percent": 48}, "memory": {"used_percent": 61}},
                "gateway": {"overall": "ok"},
                "docker": {"running": 12},
                "cron": {"abnormal_jobs": 0},
                "top_findings": ["服务全部正常"],
                "actions": ["继续观察重试队列"],
            }
        )
    elif args.layout in {"collapsible-list", "knowledge-digest"}:
        base.update(
            {
                "report_date": "2026-03-17",
                "organized_at": "2026-03-18 02:00",
                "execution_steps": [{"name": "读取昨天记忆", "status": "ok", "file": "memory/2026-03-17.md", "detail": "提炼重点"}],
                "completed_tasks": ["完成任务 A"],
                "new_topics": ["选题 A（SCORE 22/25）"],
                "insights": ["洞察 A"],
                "lessons": ["教训 A"],
            }
        )
    elif args.layout in {"grouped-panels", "daily-diary"}:
        base.update(
            {
                "date": "2026-03-17",
                "completed": ["完成项 A"],
                "highlights": ["发现 A"],
                "tomorrow_plan": ["明日计划 A"],
                "agent_sections": [{"agent": args.agent_id, "status": "ok", "task_count": 3, "highlights": [{"title": "核心推进", "desc": "完成关键动作"}]}],
                "exceptions": [{"agent": args.agent_id, "task": "示例任务", "status": "warning", "error": "这里写异常说明"}],
            }
        )
    elif args.layout in {"panel-report", "diagnosis-report"}:
        base.update(
            {
                "report_window": "近12小时",
                "stats": {"checked_jobs": 16, "abnormal_jobs": 1, "failed_jobs": 0, "delayed_jobs": 0},
                "major_findings": [{"severity": "P1", "title": "示例发现", "summary": "这里写摘要", "job_name": "示例任务"}],
                "jobs": [{"name": "示例任务", "agent": args.agent_id, "schedule": "0 9 * * *", "status": "ok", "summary": "运行正常", "findings": ["发现 A"], "suggestions": ["建议 A"]}],
            }
        )
    elif args.layout in {"distribution-summary", "distribution-report"}:
        base.update({"skill_name": "example-skill", "source": "evolution", "target_agent": args.agent_id, "match_score": 88})
    if args.channel == "topic":
        base["thread_summary"] = {
            "notice": f"{args.template_description}已完成",
            "bullets": ["摘要点 1", "摘要点 2", "详情见上一条完整卡片"],
            "footer": "详情见上一条完整卡片。",
        }
    return base


def upsert_template(registry: dict, template_name: str, template_config: dict) -> str:
    templates = registry.setdefault("templates", {})
    existed = template_name in templates
    templates[template_name] = template_config
    return "updated" if existed else "created"


def upsert_job_spec(registry: dict, job_spec: dict) -> str:
    jobs = registry.setdefault("jobs", [])
    for index, item in enumerate(jobs):
        if item.get("name") == job_spec["name"]:
            jobs[index] = job_spec
            return "updated"
    jobs.append(job_spec)
    return "created"


def main() -> int:
    args = parse_args()
    runtime_dir = Path(args.runtime_dir)
    templates_file = runtime_dir / "feishu-templates.local.json"
    jobs_spec_file = runtime_dir / "jobs-spec.local.json"
    example_file = runtime_dir / "payloads" / f"{args.template_name}.example.json"

    templates_registry = load_json(templates_file, {"templates": {}})
    jobs_registry = load_json(
        jobs_spec_file,
        {
            "version": 1,
            "defaults": {"session": "isolated", "wake": "now", "timeout_seconds": 300},
            "jobs": [],
        },
    )

    if not args.force:
        existing_template = (templates_registry.get("templates") or {}).get(args.template_name)
        if existing_template:
            raise ValueError(f"模板 {args.template_name} 已存在，若要覆盖请加 --force")
        existing_jobs = [job for job in jobs_registry.get("jobs", []) if job.get("name") == args.job_name]
        if existing_jobs:
            raise ValueError(f"任务 {args.job_name} 已存在，若要覆盖请加 --force")

    template_action = upsert_template(templates_registry, args.template_name, build_template_config(args))
    job_action = upsert_job_spec(jobs_registry, build_job_spec(args))

    write_json(templates_file, templates_registry)
    write_json(jobs_spec_file, jobs_registry)
    write_json(example_file, build_example_payload(args))

    print(
        json.dumps(
            {
                "template": {"name": args.template_name, "action": template_action, "file": str(templates_file)},
                "job": {"name": args.job_name, "action": job_action, "file": str(jobs_spec_file)},
                "payload_example": str(example_file),
                "next_steps": [
                    f"python3 scripts/sync_openclaw_jobs.py --spec-file {jobs_spec_file}",
                    f"准备好真实 payload 后，再用 scripts/send_message.py 对模板 {args.template_name} 做一次 smoke test",
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
