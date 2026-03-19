from __future__ import annotations

import json
from pathlib import Path

from openclaw_feishu_cron_kit.core import build_settings
from openclaw_feishu_cron_kit.cron_wrapper import PAYLOAD_END, PAYLOAD_FILE, PAYLOAD_START, deliver_configured_jobs, extract_payload_block


def test_extract_payload_block_supports_marker_wrapped_json() -> None:
    summary = f"""
任务完成。

{PAYLOAD_START}
```json
{{"title":"日报","timestamp":"2026-03-19 09:00","thread_summary":{{"notice":"完成","bullets":["a","b"]}}}}
```
{PAYLOAD_END}
""".strip()

    payload = extract_payload_block(summary)

    assert payload["title"] == "日报"
    assert payload["thread_summary"]["notice"] == "完成"


def test_extract_payload_block_supports_file_reference(tmp_path: Path) -> None:
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(
        json.dumps({"title": "日报", "timestamp": "2026-03-19 09:00", "thread_summary": {"notice": "完成", "bullets": ["a"]}}, ensure_ascii=False),
        encoding="utf-8",
    )
    summary = f"任务完成。\n{PAYLOAD_FILE}: {payload_path}"

    payload = extract_payload_block(summary)

    assert payload["title"] == "日报"
    assert payload["thread_summary"]["bullets"] == ["a"]


def test_extract_payload_block_discovers_latest_file_when_summary_missing(tmp_path: Path) -> None:
    payload_dir = tmp_path / "payloads"
    payload_dir.mkdir()
    older_path = payload_dir / "skill-hourly-report-older.json"
    older_path.write_text(
        json.dumps({"title": "旧日报", "timestamp": "2026-03-19 08:00", "thread_summary": {"notice": "旧", "bullets": ["a"]}}, ensure_ascii=False),
        encoding="utf-8",
    )
    older_path.touch()
    payload_path = payload_dir / "skill-hourly-report-latest.json"
    payload_path.write_text(
        json.dumps({"title": "新日报", "timestamp": "2026-03-19 09:00", "thread_summary": {"notice": "完成", "bullets": ["a"]}}, ensure_ascii=False),
        encoding="utf-8",
    )
    payload_path.touch()

    payload = extract_payload_block(
        "任务完成，但 summary 遗漏了 payload 标记。",
        payload_mode="file",
        payload_dir=payload_dir,
        payload_file_globs=["skill-hourly-report-*.json"],
        run_at_ms=0,
    )

    assert payload["title"] == "新日报"


def test_extract_payload_block_rejects_file_outside_configured_dir(tmp_path: Path) -> None:
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(
        json.dumps({"title": "日报", "timestamp": "2026-03-19 09:00", "thread_summary": {"notice": "完成", "bullets": ["a"]}}, ensure_ascii=False),
        encoding="utf-8",
    )
    summary = f"任务完成。\n{PAYLOAD_FILE}: {payload_path}"

    try:
        extract_payload_block(summary, payload_mode="file", payload_dir=tmp_path / "other")
    except ValueError as exc:
        assert "payload 文件必须位于" in str(exc)
    else:
        raise AssertionError("expected PayloadExtractionError")


def test_extract_payload_block_supports_balanced_json_without_end_marker() -> None:
    summary = f"""
任务完成。

{PAYLOAD_START}
{{"title":"日报","timestamp":"2026-03-19 09:00","thread_summary":{{"notice":"完成","bullets":["a","b"]}}}}
""".strip()

    payload = extract_payload_block(summary)

    assert payload["title"] == "日报"
    assert payload["thread_summary"]["notice"] == "完成"


def test_deliver_configured_jobs_sends_latest_undelivered_run(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "repo"
    runtime_dir = project_root / "runtime"
    examples_dir = project_root / "examples"
    scripts_dir = project_root / "scripts"
    state_dir = project_root / "state"
    logs_dir = project_root / "logs"
    runs_dir = tmp_path / "runs"
    runtime_dir.mkdir(parents=True)
    examples_dir.mkdir()
    scripts_dir.mkdir()
    state_dir.mkdir()
    logs_dir.mkdir()
    runs_dir.mkdir()
    (scripts_dir / "send_message.py").write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    (runtime_dir / "accounts.local.json").write_text(
        json.dumps({"accounts": {"main": {"app_id": "cli_main", "app_secret": "sec_main"}}}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (runtime_dir / "feishu-templates.local.json").write_text(
        json.dumps(
            {
                "templates": {
                    "daily-knowledge": {
                        "required_fields": ["title", "timestamp", "thread_summary"],
                        "route": {
                            "target": {"id": "oc_demo", "type": "chat_id"},
                            "delivery": {"channel": "topic"},
                            "policy": {"lock_target": True, "lock_delivery": True},
                            "transport": {"provider": "feishu", "account": "main"},
                            "thread": {
                                "enabled": True,
                                "binding_key_template": "main:daily-knowledge",
                                "title_template": "【每日知识整理】",
                                "summary_reply": {"enabled": True, "required": True, "channel": "post"},
                            },
                        },
                        "presentation": {"schema": "1.0", "structure": "generic", "blocks": []},
                    }
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (examples_dir / "jobs.example.json").write_text(
        json.dumps({"jobs": [{"id": "job-1", "agentId": "main"}]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    config_path = runtime_dir / "cron-delivery.local.json"
    config_path.write_text(
        json.dumps(
            {
                "version": 1,
                "jobs": [
                    {
                        "job_id": "job-1",
                        "template": "daily-knowledge",
                        "agent_id": "main",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (runs_dir / "job-1.jsonl").write_text(
        json.dumps(
            {
                "action": "finished",
                "runAtMs": 1773856800000,
                "summary": f"{PAYLOAD_START}\n{{\"title\":\"每日知识整理\",\"timestamp\":\"2026-03-19 02:00\",\"thread_summary\":{{\"notice\":\"完成\",\"bullets\":[\"a\",\"b\"]}}}}\n{PAYLOAD_END}",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    settings = build_settings(project_root=project_root, state_dir=state_dir, logs_dir=logs_dir)
    monkeypatch.setattr(
        "openclaw_feishu_cron_kit.cron_wrapper.send_template_payload",
        lambda settings, **kwargs: {
            "ok": True,
            "message_id": "om_msg_123",
            "result": {"code": 0, "data": {"message_id": "om_msg_123"}},
        },
    )

    results = deliver_configured_jobs(settings, config_path=config_path, default_runs_dir=runs_dir)
    state = json.loads((state_dir / "cron-wrapper-deliveries.json").read_text(encoding="utf-8"))

    assert results == [{"job_id": "job-1", "status": "delivered", "run_at_ms": 1773856800000, "message_id": "om_msg_123"}]
    assert state["jobs"]["job-1"]["run_at_ms"] == 1773856800000
    assert state["jobs"]["job-1"]["message_id"] == "om_msg_123"


def test_deliver_configured_jobs_reads_payload_file_reference(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "repo"
    runtime_dir = project_root / "runtime"
    examples_dir = project_root / "examples"
    scripts_dir = project_root / "scripts"
    state_dir = project_root / "state"
    logs_dir = project_root / "logs"
    runs_dir = tmp_path / "runs"
    payload_dir = tmp_path / "payloads"
    runtime_dir.mkdir(parents=True)
    examples_dir.mkdir()
    scripts_dir.mkdir()
    state_dir.mkdir()
    logs_dir.mkdir()
    runs_dir.mkdir()
    payload_dir.mkdir()
    (scripts_dir / "send_message.py").write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    (runtime_dir / "accounts.local.json").write_text(
        json.dumps({"accounts": {"main": {"app_id": "cli_main", "app_secret": "sec_main"}}}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (runtime_dir / "feishu-templates.local.json").write_text(
        json.dumps(
            {
                "templates": {
                    "daily-knowledge": {
                        "required_fields": ["title", "timestamp", "thread_summary"],
                        "route": {
                            "target": {"id": "oc_demo", "type": "chat_id"},
                            "delivery": {"channel": "topic"},
                            "policy": {"lock_target": True, "lock_delivery": True},
                            "transport": {"provider": "feishu", "account": "main"},
                            "thread": {
                                "enabled": True,
                                "binding_key_template": "main:daily-knowledge",
                                "title_template": "【每日知识整理】",
                                "summary_reply": {"enabled": True, "required": True, "channel": "post"},
                            },
                        },
                        "presentation": {"schema": "1.0", "structure": "generic", "blocks": []},
                    }
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (examples_dir / "jobs.example.json").write_text(
        json.dumps({"jobs": [{"id": "job-1", "agentId": "main"}]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    config_path = runtime_dir / "cron-delivery.local.json"
    config_path.write_text(
        json.dumps(
            {
                "version": 1,
                "jobs": [
                    {
                        "job_id": "job-1",
                        "template": "daily-knowledge",
                        "agent_id": "main",
                        "payload_mode": "file",
                        "payload_dir": str(payload_dir),
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    payload_path = payload_dir / "job-1.json"
    payload_path.write_text(
        json.dumps({"title": "每日知识整理", "timestamp": "2026-03-19 02:00", "thread_summary": {"notice": "完成", "bullets": ["a", "b"]}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (runs_dir / "job-1.jsonl").write_text(
        json.dumps(
            {
                "action": "finished",
                "runAtMs": 1773856800001,
                "summary": f"{PAYLOAD_FILE}: {payload_path}",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    settings = build_settings(project_root=project_root, state_dir=state_dir, logs_dir=logs_dir)
    monkeypatch.setattr(
        "openclaw_feishu_cron_kit.cron_wrapper.send_template_payload",
        lambda settings, **kwargs: {
            "ok": True,
            "message_id": "om_msg_456",
            "result": {"code": 0, "data": {"message_id": "om_msg_456"}},
        },
    )

    results = deliver_configured_jobs(settings, config_path=config_path, default_runs_dir=runs_dir)

    assert results == [{"job_id": "job-1", "status": "delivered", "run_at_ms": 1773856800001, "message_id": "om_msg_456"}]


def test_deliver_configured_jobs_discovers_payload_file_when_summary_marker_is_missing(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "repo"
    runtime_dir = project_root / "runtime"
    examples_dir = project_root / "examples"
    scripts_dir = project_root / "scripts"
    state_dir = project_root / "state"
    logs_dir = project_root / "logs"
    runs_dir = tmp_path / "runs"
    payload_dir = tmp_path / "payloads"
    runtime_dir.mkdir(parents=True)
    examples_dir.mkdir()
    scripts_dir.mkdir()
    state_dir.mkdir()
    logs_dir.mkdir()
    runs_dir.mkdir()
    payload_dir.mkdir()
    (scripts_dir / "send_message.py").write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    (runtime_dir / "accounts.local.json").write_text(
        json.dumps({"accounts": {"main": {"app_id": "cli_main", "app_secret": "sec_main"}}}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (runtime_dir / "feishu-templates.local.json").write_text(
        json.dumps(
            {
                "templates": {
                    "daily-knowledge": {
                        "required_fields": ["title", "timestamp", "thread_summary"],
                        "route": {
                            "target": {"id": "oc_demo", "type": "chat_id"},
                            "delivery": {"channel": "topic"},
                            "policy": {"lock_target": True, "lock_delivery": True},
                            "transport": {"provider": "feishu", "account": "main"},
                            "thread": {
                                "enabled": True,
                                "binding_key_template": "main:daily-knowledge",
                                "title_template": "【每日知识整理】",
                                "summary_reply": {"enabled": True, "required": True, "channel": "post"},
                            },
                        },
                        "presentation": {"schema": "1.0", "structure": "generic", "blocks": []},
                    }
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (examples_dir / "jobs.example.json").write_text(
        json.dumps({"jobs": [{"id": "job-1", "agentId": "main"}]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    config_path = runtime_dir / "cron-delivery.local.json"
    config_path.write_text(
        json.dumps(
            {
                "version": 1,
                "jobs": [
                    {
                        "job_id": "job-1",
                        "template": "daily-knowledge",
                        "agent_id": "main",
                        "payload_mode": "file",
                        "payload_dir": str(payload_dir),
                        "payload_file_globs": ["daily-knowledge-*.json"],
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    payload_path = payload_dir / "daily-knowledge-20260320-0200.json"
    payload_path.write_text(
        json.dumps({"title": "每日知识整理", "timestamp": "2026-03-20 02:00", "thread_summary": {"notice": "完成", "bullets": ["a", "b"]}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (runs_dir / "job-1.jsonl").write_text(
        json.dumps(
            {
                "action": "finished",
                "runAtMs": 1,
                "summary": "任务完成，但模型遗漏了 payload 文件路径。",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    settings = build_settings(project_root=project_root, state_dir=state_dir, logs_dir=logs_dir)
    monkeypatch.setattr(
        "openclaw_feishu_cron_kit.cron_wrapper.send_template_payload",
        lambda settings, **kwargs: {
            "ok": True,
            "message_id": "om_msg_789",
            "result": {"code": 0, "data": {"message_id": "om_msg_789"}},
        },
    )

    results = deliver_configured_jobs(settings, config_path=config_path, default_runs_dir=runs_dir)

    assert results == [{"job_id": "job-1", "status": "delivered", "run_at_ms": 1, "message_id": "om_msg_789"}]
