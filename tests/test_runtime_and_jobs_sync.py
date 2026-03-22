from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path
from typing import Any

from openclaw_feishu_cron_kit.core import (
    build_settings,
    build_settings_from_args,
    load_account_credentials,
    resolve_thread_options,
    send_template_payload,
)
from openclaw_feishu_cron_kit.presentation_presets import load_template_presentations
from pathlib import Path as _PresPath

_TEMPLATES_FILE = _PresPath(__file__).resolve().parents[1] / "runtime" / "feishu-templates.local.json"
_TEMPLATE_PRESENTATIONS = load_template_presentations(_TEMPLATES_FILE)
from openclaw_feishu_cron_kit.jobs_sync import (
    TEMP_JOB_ID_PLACEHOLDER,
    build_add_command,
    build_edit_command,
    build_schedule_flags,
    format_openclaw_duration,
    merge_job_defaults,
    normalize_job_spec,
    parse_openclaw_json_output,
    render_job_text,
)


def test_build_settings_prefers_runtime_local_files(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    scripts_dir = project_root / "scripts"
    runtime_dir = project_root / "runtime"
    examples_dir = project_root / "examples"
    scripts_dir.mkdir(parents=True)
    runtime_dir.mkdir()
    examples_dir.mkdir()

    entry_script = scripts_dir / "send_message.py"
    entry_script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    (runtime_dir / "feishu-templates.local.json").write_text("{}", encoding="utf-8")
    (runtime_dir / "accounts.local.json").write_text("{}", encoding="utf-8")
    (examples_dir / "feishu-templates.example.json").write_text("{}", encoding="utf-8")
    (examples_dir / "accounts.example.json").write_text("{}", encoding="utf-8")
    (examples_dir / "jobs.example.json").write_text('{"jobs":[]}', encoding="utf-8")

    args = Namespace(
        templates_file=None,
        jobs_file=None,
        accounts_file=None,
        openclaw_config_file=None,
        state_dir=None,
        logs_dir=None,
    )
    settings = build_settings_from_args(args, entry_script=entry_script)

    assert settings.runtime_dir == runtime_dir
    assert settings.templates_file == runtime_dir / "feishu-templates.local.json"
    assert settings.accounts_file == runtime_dir / "accounts.local.json"
    assert settings.jobs_file == examples_dir / "jobs.example.json"


def test_load_account_credentials_accepts_openclaw_json_shape(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    examples_dir = project_root / "examples"
    examples_dir.mkdir()
    (examples_dir / "feishu-templates.example.json").write_text("{}", encoding="utf-8")
    (examples_dir / "jobs.example.json").write_text('{"jobs":[]}', encoding="utf-8")
    openclaw_config = tmp_path / "openclaw.json"
    openclaw_config.write_text(
        """
        {
          "channels": {
            "feishu": {
              "accounts": {
                "main": {"appId": "cli_main", "appSecret": "sec_main"},
                "blogger": {"appId": "cli_blogger", "appSecret": "sec_blogger"}
              }
            }
          }
        }
        """.strip(),
        encoding="utf-8",
    )

    settings = Namespace(
        project_root=project_root,
        runtime_dir=project_root / "runtime",
        templates_file=examples_dir / "feishu-templates.example.json",
        jobs_file=examples_dir / "jobs.example.json",
        accounts_file=project_root / "runtime" / "accounts.local.json",
        openclaw_config_file=openclaw_config,
        state_dir=project_root / "state",
        logs_dir=project_root / "logs",
        entry_script=project_root / "scripts" / "send_message.py",
    )

    assert load_account_credentials(settings, "blogger") == ("cli_blogger", "sec_blogger")
    assert load_account_credentials(settings, "unknown") == ("cli_main", "sec_main")


def test_jobs_sync_builds_commands_with_real_job_id_placeholders() -> None:
    defaults = {
        "session": "isolated",
        "wake": "next-heartbeat",
        "timeout_seconds": 300,
    }
    raw_job = {
        "name": "深度选题研究",
        "agent": "blogger",
        "schedule": {"kind": "cron", "expr": "0 6 * * *", "tz": "Asia/Shanghai"},
        "payload": {
            "kind": "agentTurn",
            "message": "python3 scripts/send_message.py --job-id \"{{job_id}}\"",
        },
    }
    job = normalize_job_spec(merge_job_defaults(defaults, raw_job))

    assert render_job_text(raw_job["payload"]["message"], "job-123") == 'python3 scripts/send_message.py --job-id "job-123"'

    add_command = build_add_command("openclaw", job)
    assert TEMP_JOB_ID_PLACEHOLDER in add_command[-1]
    assert "--cron" in add_command
    assert "--agent" in add_command

    edit_command = build_edit_command("openclaw", job, "job-123", "job-123")
    assert 'python3 scripts/send_message.py --job-id "job-123"' in edit_command
    assert "--enable" in edit_command


def test_parse_openclaw_json_output_skips_plugin_banner() -> None:
    raw = """
    [plugins] feishu_chat: Registered feishu_chat
    [plugins] feishu_doc: Registered feishu_fetch_doc
    {
      "jobs": [
        {"id": "job-1", "name": "demo"}
      ]
    }
    """.strip()

    payload = parse_openclaw_json_output(raw)

    assert payload["jobs"][0]["id"] == "job-1"


def test_format_openclaw_duration_supports_ms_fields() -> None:
    assert format_openclaw_duration(10800000) == "3h"
    assert format_openclaw_duration("300000") == "5m"


def test_build_schedule_flags_supports_every_ms_and_stagger_ms() -> None:
    job = normalize_job_spec(
        {
            "name": "每3小时任务",
            "agent": "blogger",
            "schedule": {"kind": "every", "everyMs": 10800000, "staggerMs": 300000},
            "payload": {"kind": "agentTurn", "message": "echo ok"},
        }
    )

    flags = build_schedule_flags(job)

    assert flags == ["--every", "3h", "--stagger", "5m"]


def test_send_template_payload_supports_runtime_api_usage(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "repo"
    runtime_dir = project_root / "runtime"
    examples_dir = project_root / "examples"
    scripts_dir = project_root / "scripts"
    runtime_dir.mkdir(parents=True)
    examples_dir.mkdir()
    scripts_dir.mkdir()
    (scripts_dir / "send_message.py").write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    (runtime_dir / "accounts.local.json").write_text(
        json.dumps({"accounts": {"task": {"app_id": "cli_task", "app_secret": "sec_task"}}}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (runtime_dir / "feishu-templates.local.json").write_text(
        json.dumps(
            {
                "templates": {
                    "daily-task": {
                        "description": "今日任务清单",
                        "required_fields": ["title", "summary", "date", "weekday", "timestamp"],
                        "route": {
                            "target": {"id": "on_demo", "type": "union_id"},
                            "delivery": {"channel": "direct"},
                            "policy": {"lock_target": True, "lock_delivery": True},
                            "transport": {"provider": "feishu", "account": "task"},
                        },
                        "presentation": {
                            "schema": "1.0",
                            "structure": "generic",
                            "blocks": [
                                {"type": "markdown", "template": "✅ **今日任务速览**\n{summary}"},
                                {"type": "facts", "title": "执行信息", "items": [
                                    {"label": "日期", "path": "date"},
                                    {"label": "星期", "path": "weekday"},
                                    {"label": "时间", "path": "timestamp"},
                                ]},
                            ],
                        },
                    }
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (examples_dir / "jobs.example.json").write_text('{"jobs":[]}', encoding="utf-8")

    settings = build_settings(project_root=project_root)

    monkeypatch.setattr("openclaw_feishu_cron_kit.core.get_tenant_access_token", lambda app_id, app_secret: "tenant-token")
    monkeypatch.setattr(
        "openclaw_feishu_cron_kit.core.dispatch_message",
        lambda settings, access_token, route, msg_type, content_payload, thread_options=None: {
            "ok": True,
            "result": {"code": 0, "data": {"message_id": "om_msg_123"}},
        },
    )

    outcome = send_template_payload(
        settings,
        template_name="daily-task",
        data={
            "title": "超级峰今日任务",
            "summary": "今天共有 2 个重点任务。",
            "date": "3月18日",
            "weekday": "周三",
            "timestamp": "2026-03-18 08:00",
            "p0_tasks": [{"task": "修复模板链路", "note": "完成后验证"}],
            "p1_tasks": [{"task": "整理发布说明", "note": "同步 README"}],
        },
        agent_id="task",
    )

    assert outcome["ok"] is True
    assert outcome["message_id"] == "om_msg_123"
    assert outcome["route"]["delivery"]["channel"] == "direct"


def test_send_template_payload_sends_thread_followup_cards(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "repo"
    runtime_dir = project_root / "runtime"
    examples_dir = project_root / "examples"
    scripts_dir = project_root / "scripts"
    runtime_dir.mkdir(parents=True)
    examples_dir.mkdir()
    scripts_dir.mkdir()
    (scripts_dir / "send_message.py").write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    (runtime_dir / "accounts.local.json").write_text(
        json.dumps({"accounts": {"product": {"app_id": "cli_product", "app_secret": "sec_product"}}}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (runtime_dir / "feishu-templates.local.json").write_text(
        json.dumps(
            {
                "templates": {
                    "website-analytics-daily": {
                        "description": "网站产品数据简报",
                        "required_fields": [
                            "product_key",
                            "product_name",
                            "domain",
                            "report_date",
                            "headline",
                            "traffic_metrics",
                            "search_metrics",
                            "quality_metrics",
                        ],
                        "route": {
                            "target": {"id": "oc_demo", "type": "chat_id"},
                            "delivery": {"channel": "topic"},
                            "policy": {"lock_target": True, "lock_delivery": True},
                            "transport": {"provider": "feishu", "account": "product"},
                            "thread": {
                                "enabled": True,
                                "binding_key_template": "product:website-analytics:{product_key}",
                                "title_template": "【{product_name} 数据简报】",
                                "summary_reply": {"enabled": False, "required": False, "channel": "text"},
                            },
                        },
                        "presentation": _TEMPLATE_PRESENTATIONS["website-analytics-daily"],
                    },
                    "website-analytics-daily-detail": {
                        "description": "网站产品数据简报详情卡",
                        "required_fields": [
                            "product_key",
                            "product_name",
                            "domain",
                            "report_date",
                            "headline",
                            "channel_detail_rows",
                            "landing_pages",
                            "conversion_pages",
                        ],
                        "presentation": {
                            "schema": "2.0",
                            "structure": "table-report",
                            "header_title_template": "🧭 {product_name} 渠道与页面明细 · {report_date}",
                            "config": {"width_mode": "fill"},
                            "blocks": [
                                {"type": "plain_text", "template": "{headline}"},
                                {"type": "markdown", "template": "**渠道明细**"},
                            ],
                        },
                    },
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (examples_dir / "jobs.example.json").write_text('{"jobs":[]}', encoding="utf-8")

    settings = build_settings(project_root=project_root)

    monkeypatch.setattr("openclaw_feishu_cron_kit.core.get_tenant_access_token", lambda app_id, app_secret: "tenant-token")

    calls: list[dict[str, Any]] = []

    def fake_dispatch(settings, access_token, route, msg_type, content_payload, thread_options=None):
        calls.append(
            {
                "msg_type": msg_type,
                "content_payload": content_payload,
                "thread_options": thread_options,
            }
        )
        return {
            "ok": True,
            "result": {"code": 0, "data": {"message_id": f"om_msg_{len(calls)}", "root_id": "om_root_1"}},
        }

    monkeypatch.setattr("openclaw_feishu_cron_kit.core.dispatch_message", fake_dispatch)

    outcome = send_template_payload(
        settings,
        template_name="website-analytics-daily",
        data={
            "product_key": "ainativehub",
            "product_name": "AI Native Hub",
            "domain": "https://ainativehub.com",
            "report_date": "2026-03-20",
            "headline": "AI Native Hub 每日数据简报",
            "traffic_metrics": [],
            "search_metrics": [],
            "quality_metrics": [],
            "channel_top_rows": [],
            "alerts": [],
            "insights": [],
            "source_explanations": [],
            "thread_followups": [
                {
                    "template_name": "website-analytics-daily-detail",
                    "data": {
                        "product_key": "ainativehub",
                        "product_name": "AI Native Hub",
                        "domain": "https://ainativehub.com",
                        "report_date": "2026-03-20",
                        "headline": "AI Native Hub 渠道与页面明细",
                        "channel_detail_rows": [],
                        "landing_pages": [],
                        "conversion_pages": [],
                    },
                }
            ],
        },
        agent_id="product",
    )

    assert outcome["ok"] is True
    assert len(calls) == 2
    assert calls[0]["msg_type"] == "interactive"
    assert calls[0]["content_payload"]["header"]["title"]["content"] == "📈 AI Native Hub 数据简报 · 2026-03-20"
    assert calls[1]["content_payload"]["header"]["title"]["content"] == "🧭 AI Native Hub 渠道与页面明细 · 2026-03-20"
    assert outcome["followup_results"][0]["template_name"] == "website-analytics-daily-detail"
    assert outcome["followup_results"][0]["ok"] is True


def test_resolve_thread_options_renders_templates_from_payload() -> None:
    args = Namespace(
        thread_mode="auto",
        thread_key=None,
        thread_title=None,
        job_id="job-analytics-1",
        agent_id="product",
    )
    route = {
        "target": {"id": "oc_demo", "type": "chat_id"},
        "delivery": {"channel": "topic"},
        "thread": {
            "enabled": True,
            "binding_key_template": "product:website-analytics:{product_key}",
            "title_template": "【{product_name} 数据简报】",
            "recreate_on_root_missing": True,
            "summary_reply": {"enabled": True, "required": True, "channel": "post"},
        },
    }
    options = resolve_thread_options(
        args,
        template_name="website-analytics-daily",
        template_config={"description": "网站产品数据简报"},
        route=route,
        data={"product_key": "ainativehub", "product_name": "AI Native Hub"},
    )

    assert options is not None
    assert options["binding_key"] == "product:website-analytics:ainativehub"
    assert options["title"] == "【AI Native Hub 数据简报】"
