from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import requests

from .renderer import build_generic_card, build_summary_post
from .storage import append_jsonl, load_json_file, save_json_file

DELIVERY_CHANNELS = {"direct", "message", "topic"}
USER_TARGET_TYPES = {"open_id", "union_id", "user_id", "email"}
GROUP_TARGET_TYPES = {"chat_id"}
THREAD_MODES = {"auto", "off", "new", "reply"}
RETRYABLE_HTTP_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}
RETRYABLE_ERROR_TOKENS = [
    "timeout",
    "timed out",
    "temporarily",
    "temporary",
    "rate limit",
    "too many requests",
    "internal error",
    "service unavailable",
    "bad gateway",
    "gateway timeout",
    "connection reset",
    "connection refused",
    "network is unreachable",
    "proxy error",
]
RETRY_DELAY_SECONDS = {1: 5 * 60, 2: 30 * 60}
RETRY_MAX_ATTEMPTS = 3


@dataclass
class AppSettings:
    project_root: Path
    templates_file: Path
    jobs_file: Path | None
    accounts_file: Path | None
    state_dir: Path
    logs_dir: Path
    entry_script: Path

    @property
    def bindings_file(self) -> Path:
        return self.state_dir / "feishu-thread-bindings.json"

    @property
    def retry_queue_file(self) -> Path:
        return self.state_dir / "feishu-retry-queue.json"

    @property
    def send_audit_log(self) -> Path:
        return self.logs_dir / "feishu-send-audit.jsonl"

    @property
    def thread_audit_log(self) -> Path:
        return self.logs_dir / "feishu-thread-audit.jsonl"

    @property
    def retry_audit_log(self) -> Path:
        return self.logs_dir / "feishu-retry-audit.jsonl"


def iso_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def load_template_registry(settings: AppSettings) -> dict[str, Any]:
    return json.loads(settings.templates_file.read_text(encoding="utf-8"))


def get_template_config(registry: dict[str, Any], template_name: str) -> dict[str, Any]:
    templates = registry.get("templates", registry)
    template = templates.get(template_name)
    if not template:
        raise ValueError(f"未知模板: {template_name}")
    return template


def normalize_route_config(raw_value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw_value, dict):
        raise ValueError(f"无效 route 配置: {raw_value}")
    target = raw_value.get("target") or {}
    delivery = raw_value.get("delivery") or {}
    policy = raw_value.get("policy") or {}
    thread = raw_value.get("thread") or {}

    target_type = target.get("type")
    if target_type not in USER_TARGET_TYPES | GROUP_TARGET_TYPES:
        raise ValueError(f"无效 target.type: {target_type}")
    channel = delivery.get("channel")
    if channel not in DELIVERY_CHANNELS:
        raise ValueError(f"无效 delivery.channel: {channel}")
    if channel == "direct" and target_type not in USER_TARGET_TYPES:
        raise ValueError("direct 通道只允许私聊目标")
    if channel in {"message", "topic"} and target_type not in GROUP_TARGET_TYPES:
        raise ValueError("message/topic 通道只允许群目标")

    return {
        "target": {"id": str(target.get("id")), "type": target_type},
        "delivery": {"channel": channel},
        "policy": {
            "lock_target": bool(policy.get("lock_target", False)),
            "lock_delivery": bool(policy.get("lock_delivery", False)),
        },
        "thread": {
            "enabled": bool(thread.get("enabled", False)),
            "binding_key_template": str(thread.get("binding_key_template", "")).strip(),
            "title_template": str(thread.get("title_template", "")).strip(),
            "recreate_on_root_missing": bool(thread.get("recreate_on_root_missing", True)),
            "summary_reply": {
                "enabled": bool((thread.get("summary_reply") or {}).get("enabled", False)),
                "required": bool((thread.get("summary_reply") or {}).get("required", False)),
                "channel": str((thread.get("summary_reply") or {}).get("channel", "post")).strip() or "post",
                "mention_open_ids": [str(item).strip() for item in ((thread.get("summary_reply") or {}).get("mention_open_ids") or []) if str(item).strip()],
            },
        },
    }


def resolve_route(template_config: dict[str, Any], cli_overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    route = normalize_route_config(template_config.get("route") or {})
    if not cli_overrides:
        return route

    if cli_overrides.get("target_id"):
        if route["policy"]["lock_target"]:
            raise ValueError("模板已锁定 target，禁止覆盖 target_id")
        route["target"]["id"] = cli_overrides["target_id"]

    if cli_overrides.get("target_type"):
        if route["policy"]["lock_target"]:
            raise ValueError("模板已锁定 target，禁止覆盖 target_type")
        route["target"]["type"] = cli_overrides["target_type"]

    if cli_overrides.get("delivery_channel"):
        if route["policy"]["lock_delivery"]:
            raise ValueError("模板已锁定 delivery，禁止覆盖 delivery_channel")
        route["delivery"]["channel"] = cli_overrides["delivery_channel"]

    return normalize_route_config(route)


def load_jobs_registry(settings: AppSettings, jobs_file: Path | None = None) -> dict[str, Any] | None:
    target = jobs_file or settings.jobs_file
    if not target or not target.exists():
        return None
    return json.loads(target.read_text(encoding="utf-8"))


def validate_known_job_id(settings: AppSettings, job_id: str | None, jobs_file: Path | None, agent_id: str | None) -> dict[str, Any] | None:
    if not job_id:
        return None
    registry = load_jobs_registry(settings, jobs_file=jobs_file)
    if not registry:
        raise ValueError("未找到 jobs 配置文件，无法校验 job_id")
    for job in registry.get("jobs", []):
        if str(job.get("id")) == str(job_id):
            if agent_id and str(job.get("agentId") or "") and str(job.get("agentId")) != str(agent_id):
                raise ValueError(f"job_id={job_id} 的 agentId 与当前 agent_id={agent_id} 不一致")
            return job
    raise ValueError(f"未在 jobs 配置中找到 job_id={job_id}")


def build_default_thread_key(agent_id: str, template_name: str, target_id: str) -> str:
    raw = f"{agent_id}:{template_name}:{target_id}"
    return f"topic:{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:12]}"


def resolve_thread_options(args: argparse.Namespace, template_name: str, template_config: dict[str, Any], route: dict[str, Any], data: dict[str, Any]) -> dict[str, Any] | None:
    if route["delivery"]["channel"] != "topic":
        return None
    mode = args.thread_mode or "auto"
    if mode == "off":
        return None
    thread_config = route.get("thread") or {}
    enabled = thread_config.get("enabled") or mode in {"new", "reply"}
    if not enabled:
        return None

    binding_key = thread_config.get("binding_key_template") or args.thread_key or (f"job:{args.job_id}" if args.job_id else build_default_thread_key(args.agent_id or "default", template_name, route["target"]["id"]))
    title = args.thread_title or thread_config.get("title_template") or data.get("title") or template_config.get("description") or template_name
    return {
        "mode": mode,
        "binding_key": binding_key,
        "title": title,
        "recreate_on_root_missing": bool(thread_config.get("recreate_on_root_missing", True)),
        "summary_reply": thread_config.get("summary_reply") or {},
        "template_name": template_name,
        "job_id": args.job_id,
        "agent_id": args.agent_id,
        "target_id": route["target"]["id"],
        "target_type": route["target"]["type"],
    }


def load_thread_bindings(settings: AppSettings) -> dict[str, Any]:
    payload = load_json_file(settings.bindings_file, {"version": 1, "bindings": {}})
    if not isinstance(payload, dict):
        payload = {"version": 1, "bindings": {}}
    if not isinstance(payload.get("bindings"), dict):
        payload["bindings"] = {}
    return payload


def save_thread_bindings(settings: AppSettings, payload: dict[str, Any]) -> None:
    save_json_file(settings.bindings_file, payload)


def load_retry_queue(settings: AppSettings) -> dict[str, Any]:
    payload = load_json_file(settings.retry_queue_file, {"version": 1, "records": []})
    if not isinstance(payload, dict):
        payload = {"version": 1, "records": []}
    if not isinstance(payload.get("records"), list):
        payload["records"] = []
    return payload


def save_retry_queue(settings: AppSettings, payload: dict[str, Any]) -> None:
    save_json_file(settings.retry_queue_file, payload)


def write_send_audit(settings: AppSettings, status: str, agent_id: str | None, mode: str, route: dict[str, Any] | None = None, template_name: str | None = None, detail: str | None = None, response_meta: dict[str, Any] | None = None) -> None:
    payload = {
        "timestamp": iso_now(),
        "status": status,
        "agent_id": agent_id,
        "mode": mode,
        "template": template_name,
    }
    if route:
        payload["target_id"] = route["target"]["id"]
        payload["target_type"] = route["target"]["type"]
        payload["delivery_channel"] = route["delivery"]["channel"]
    if detail:
        payload["detail"] = detail
    if response_meta:
        payload["response"] = response_meta
    append_jsonl(settings.send_audit_log, payload)


def write_thread_audit(settings: AppSettings, action: str, binding_key: str, record: dict[str, Any] | None = None, detail: str | None = None, response_meta: dict[str, Any] | None = None) -> None:
    payload = {"timestamp": iso_now(), "action": action, "binding_key": binding_key}
    if record:
        payload["record"] = record
    if detail:
        payload["detail"] = detail
    if response_meta:
        payload["response"] = response_meta
    append_jsonl(settings.thread_audit_log, payload)


def write_retry_audit(settings: AppSettings, action: str, record: dict[str, Any] | None = None, detail: str | None = None) -> None:
    payload = {"timestamp": iso_now(), "action": action}
    if record:
        payload["record"] = record
    if detail:
        payload["detail"] = detail
    append_jsonl(settings.retry_audit_log, payload)


def load_account_credentials(settings: AppSettings, agent_id: str | None) -> tuple[str, str]:
    env_app_id = os.environ.get("FEISHU_APP_ID")
    env_app_secret = os.environ.get("FEISHU_APP_SECRET")
    if env_app_id and env_app_secret:
        return env_app_id, env_app_secret

    if settings.accounts_file and settings.accounts_file.exists():
        data = json.loads(settings.accounts_file.read_text(encoding="utf-8"))
        accounts = data.get("accounts", data)
        if agent_id and agent_id in accounts:
            account = accounts[agent_id]
        else:
            account = accounts.get("default") or accounts.get("main")
        if account and account.get("app_id") and account.get("app_secret"):
            return account["app_id"], account["app_secret"]

    raise ValueError("未提供飞书凭证，请配置 FEISHU_APP_ID / FEISHU_APP_SECRET，或提供 accounts 文件")


def parse_response_json(response: requests.Response) -> dict[str, Any]:
    try:
        payload = response.json()
        if isinstance(payload, dict):
            payload["_http_status"] = response.status_code
        return payload
    except Exception:
        return {"code": -1, "msg": f"HTTP {response.status_code}", "_http_status": response.status_code, "raw": response.text[:500]}


def execute_feishu_request(url: str, headers: dict[str, str], payload: dict[str, Any], label: str) -> dict[str, Any]:
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
    except requests.RequestException as exc:
        result = {"code": -1, "msg": f"request_error: {exc}", "raw": str(exc)}
        print(f"❌ {label}发送失败: {result}")
        return {"ok": False, "result": result}

    result = parse_response_json(response)
    if result.get("code") == 0:
        print(f"✅ {label}发送成功")
        return {"ok": True, "result": result}
    print(f"❌ {label}发送失败: {result}")
    return {"ok": False, "result": result}


def get_tenant_access_token(app_id: str, app_secret: str) -> str:
    response = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=30,
    )
    payload = response.json()
    if payload.get("code") != 0:
        raise ValueError(f"获取 access token 失败: {payload}")
    return payload["tenant_access_token"]


def post_message_request(access_token: str, route: dict[str, Any], msg_type: str, content_payload: dict[str, Any], label: str) -> dict[str, Any]:
    url = f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type={route['target']['type']}"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    payload = {"receive_id": route["target"]["id"], "msg_type": msg_type, "content": json.dumps(content_payload, ensure_ascii=False)}
    return execute_feishu_request(url, headers, payload, label)


def reply_message_request(access_token: str, root_message_id: str, msg_type: str, content_payload: dict[str, Any], label: str) -> dict[str, Any]:
    url = f"https://open.feishu.cn/open-apis/im/v1/messages/{root_message_id}/reply"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    payload = {"msg_type": msg_type, "content": json.dumps(content_payload, ensure_ascii=False), "reply_in_thread": True}
    return execute_feishu_request(url, headers, payload, label)


def extract_message_id(result_meta: dict[str, Any] | None) -> str | None:
    return ((result_meta or {}).get("data") or {}).get("message_id")


def is_root_message_missing(result_meta: dict[str, Any] | None) -> bool:
    payload = json.dumps(result_meta or {}, ensure_ascii=False).lower()
    return "message_id" in payload and any(token in payload for token in ["not exist", "not existed", "invalid", "not found"])


def build_thread_record(thread_options: dict[str, Any], root_message_id: str, response_meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "active",
        "binding_key": thread_options["binding_key"],
        "agent_id": thread_options["agent_id"],
        "template_name": thread_options["template_name"],
        "job_id": thread_options["job_id"],
        "chat_id": thread_options["target_id"],
        "target_type": thread_options["target_type"],
        "delivery_channel": "topic",
        "title": thread_options["title"],
        "root_message_id": root_message_id,
        "thread_id": ((response_meta or {}).get("data") or {}).get("thread_id"),
        "created_at": iso_now(),
        "last_sent_at": iso_now(),
        "last_reply_message_id": root_message_id,
        "failure_count": 0,
    }


def dispatch_topic_message(settings: AppSettings, access_token: str, route: dict[str, Any], msg_type: str, content_payload: dict[str, Any], thread_options: dict[str, Any] | None) -> dict[str, Any]:
    if not thread_options:
        return post_message_request(access_token, route, msg_type, content_payload, "群话题消息")

    payload = load_thread_bindings(settings)
    record = payload["bindings"].get(thread_options["binding_key"])
    if thread_options["mode"] == "new":
        record = None

    if record and record.get("status") == "active" and record.get("root_message_id"):
        result = reply_message_request(access_token, record["root_message_id"], msg_type, content_payload, "群话题回复")
        if result["ok"]:
            record["last_sent_at"] = iso_now()
            record["last_reply_message_id"] = extract_message_id(result["result"]) or record["last_reply_message_id"]
            record["failure_count"] = 0
            payload["bindings"][thread_options["binding_key"]] = record
            save_thread_bindings(settings, payload)
            write_thread_audit(settings, "reply", thread_options["binding_key"], record=record, response_meta=result["result"])
            return result

        record["failure_count"] = int(record.get("failure_count", 0)) + 1
        if thread_options["recreate_on_root_missing"] and is_root_message_missing(result["result"]):
            record["status"] = "broken"
            payload["bindings"][thread_options["binding_key"]] = record
            save_thread_bindings(settings, payload)
            write_thread_audit(settings, "broken", thread_options["binding_key"], record=record, detail="root_message_id 不可用，准备重建", response_meta=result["result"])
            record = None
        else:
            payload["bindings"][thread_options["binding_key"]] = record
            save_thread_bindings(settings, payload)
            write_thread_audit(settings, "reply_failed", thread_options["binding_key"], record=record, response_meta=result["result"])
            return result

    if thread_options["mode"] == "reply" and not record:
        raise ValueError(f"未找到固定话题绑定: {thread_options['binding_key']}")

    result = post_message_request(access_token, route, msg_type, content_payload, "群话题消息")
    if result["ok"]:
        root_message_id = extract_message_id(result["result"])
        if not root_message_id:
            raise ValueError("固定话题创建成功但未返回 message_id")
        record = build_thread_record(thread_options, root_message_id, result["result"])
        payload["bindings"][thread_options["binding_key"]] = record
        save_thread_bindings(settings, payload)
        write_thread_audit(settings, "create", thread_options["binding_key"], record=record, response_meta=result["result"])
    return result


def dispatch_message(settings: AppSettings, access_token: str, route: dict[str, Any], msg_type: str, content_payload: dict[str, Any], thread_options: dict[str, Any] | None = None) -> dict[str, Any]:
    channel = route["delivery"]["channel"]
    if channel == "direct":
        return post_message_request(access_token, route, msg_type, content_payload, "私聊消息")
    if channel == "message":
        return post_message_request(access_token, route, msg_type, content_payload, "群普通消息")
    if channel == "topic":
        return dispatch_topic_message(settings, access_token, route, msg_type, content_payload, thread_options)
    raise ValueError(f"未知 delivery.channel: {channel}")


def extract_thread_summary_data(thread_options: dict[str, Any] | None, data: dict[str, Any]) -> dict[str, Any] | None:
    summary_config = (thread_options or {}).get("summary_reply") or {}
    raw_summary = data.get("thread_summary")
    if not summary_config.get("enabled"):
        return None
    if not isinstance(raw_summary, dict):
        if summary_config.get("required"):
            raise ValueError("固定话题模板必须提供 thread_summary")
        return None

    notice = str(raw_summary.get("notice", "")).strip()
    bullets = raw_summary.get("bullets") or []
    footer = str(raw_summary.get("footer", "")).strip()
    mention_open_ids = raw_summary.get("mention_open_ids") or summary_config.get("mention_open_ids") or []
    if not isinstance(bullets, list):
        raise ValueError("thread_summary.bullets 必须是数组")
    if not isinstance(mention_open_ids, list):
        raise ValueError("thread_summary.mention_open_ids 必须是数组")
    bullets = [str(item).strip() for item in bullets if str(item).strip()]
    mention_open_ids = [str(item).strip() for item in mention_open_ids if str(item).strip()]
    if summary_config.get("required") and (not notice or not bullets):
        raise ValueError("thread_summary 必须包含 notice 和非空 bullets")
    if not notice or not bullets:
        return None
    return {"notice": notice, "bullets": bullets, "footer": footer, "mention_open_ids": mention_open_ids}


def maybe_send_thread_summary_reply(settings: AppSettings, access_token: str, thread_options: dict[str, Any] | None, response_meta: dict[str, Any], data: dict[str, Any]) -> dict[str, Any] | None:
    summary_data = extract_thread_summary_data(thread_options, data)
    if not summary_data:
        return None
    root_message_id = ((response_meta or {}).get("data") or {}).get("root_id") or ((response_meta or {}).get("data") or {}).get("message_id")
    if not root_message_id:
        raise ValueError("未能解析 root_message_id，无法发送摘要 reply")
    content = build_summary_post(thread_options["title"], summary_data)
    return reply_message_request(access_token, root_message_id, "post", content, "群话题摘要回复")


def load_retry_record(settings: AppSettings, record_id: str) -> dict[str, Any] | None:
    queue = load_retry_queue(settings)
    for record in queue.get("records", []):
        if record.get("id") == record_id:
            return record
    return None


def next_retry_at_for_attempt(attempts_made: int) -> str | None:
    delay = RETRY_DELAY_SECONDS.get(int(attempts_made))
    if not delay:
        return None
    return (datetime.now() + timedelta(seconds=delay)).isoformat(timespec="seconds")


def extract_error_text(result_meta: dict[str, Any] | None = None, detail: str | None = None) -> str:
    chunks: list[str] = []
    if detail:
        chunks.append(str(detail))
    if result_meta:
        for key in ("msg", "message", "raw", "_http_status"):
            value = result_meta.get(key)
            if value not in (None, ""):
                chunks.append(str(value))
        chunks.append(json.dumps(result_meta, ensure_ascii=False))
    return " | ".join(chunks).lower()


def is_retryable_error(result_meta: dict[str, Any] | None = None, detail: str | None = None) -> bool:
    if result_meta and isinstance(result_meta.get("_http_status"), int) and result_meta["_http_status"] in RETRYABLE_HTTP_STATUS:
        return True
    text = extract_error_text(result_meta=result_meta, detail=detail)
    return any(token in text for token in RETRYABLE_ERROR_TOKENS)


def serialize_retry_args(args: argparse.Namespace) -> dict[str, Any]:
    keys = [
        "mode",
        "template",
        "data",
        "content",
        "agent_id",
        "target_id",
        "target_type",
        "delivery_channel",
        "job_id",
        "jobs_file",
        "thread_mode",
        "thread_key",
        "thread_title",
        "templates_file",
        "accounts_file",
        "state_dir",
        "logs_dir",
    ]
    return {key: getattr(args, key, None) for key in keys}


def build_retry_fingerprint(args_map: dict[str, Any]) -> str:
    raw = json.dumps({key: args_map.get(key) for key in sorted(args_map)}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def enqueue_retry(settings: AppSettings, args: argparse.Namespace, agent_id: str | None, template_name: str | None, route: dict[str, Any] | None = None, detail: str | None = None, response_meta: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if getattr(args, "disable_retry_queue", False) or getattr(args, "mode", None) == "retry-pending":
        return None
    if not is_retryable_error(result_meta=response_meta, detail=detail):
        return None

    queue = load_retry_queue(settings)
    args_map = serialize_retry_args(args)
    if not args_map.get("agent_id"):
        args_map["agent_id"] = agent_id
    fingerprint = build_retry_fingerprint(args_map)
    for existing in queue["records"]:
        if existing.get("fingerprint") == fingerprint and existing.get("status") == "pending":
            existing["updated_at"] = iso_now()
            existing["last_error"] = detail or response_meta
            save_retry_queue(settings, queue)
            write_retry_audit(settings, "dedupe_skip", record=existing, detail="待补发记录已存在，跳过重复入队")
            return existing

    record = {
        "id": str(uuid4()),
        "fingerprint": fingerprint,
        "status": "pending",
        "created_at": iso_now(),
        "updated_at": iso_now(),
        "next_retry_at": next_retry_at_for_attempt(1),
        "attempts_made": 1,
        "max_attempts": RETRY_MAX_ATTEMPTS,
        "mode": args.mode,
        "agent_id": agent_id,
        "template": template_name,
        "job_id": args.job_id,
        "route": f"{route['delivery']['channel']}:{route['target']['type']}:{route['target']['id']}" if route else None,
        "args": args_map,
        "last_error": detail or response_meta,
    }
    queue["records"].append(record)
    save_retry_queue(settings, queue)
    write_retry_audit(settings, "queued", record=record, detail="首次发送失败，已加入补发队列")
    print(f"⏳ 已加入补发队列：{record['id']}，将在 {record['next_retry_at']} 发起第 2 次尝试")
    return record


def build_retry_command(settings: AppSettings, record: dict[str, Any]) -> list[str]:
    args_map = record.get("args") or {}
    mode = args_map.get("mode") or "template"
    command = [sys.executable or "python3", str(settings.entry_script), "--mode", mode, "--disable-retry-queue"]
    for key, flag in [
        ("template", "--template"),
        ("data", "--data"),
        ("content", "--content"),
        ("agent_id", "--agent-id"),
        ("target_id", "--target-id"),
        ("target_type", "--target-type"),
        ("delivery_channel", "--delivery-channel"),
        ("job_id", "--job-id"),
        ("jobs_file", "--jobs-file"),
        ("thread_mode", "--thread-mode"),
        ("thread_key", "--thread-key"),
        ("thread_title", "--thread-title"),
        ("templates_file", "--templates-file"),
        ("accounts_file", "--accounts-file"),
        ("state_dir", "--state-dir"),
        ("logs_dir", "--logs-dir"),
    ]:
        value = args_map.get(key)
        if value not in (None, ""):
            command.extend([flag, str(value)])
    return command


def process_retry_queue(settings: AppSettings, retry_limit: int = 10) -> int:
    queue = load_retry_queue(settings)
    now = datetime.now()
    due_records = []
    for record in queue.get("records", []):
        if record.get("status") != "pending":
            continue
        next_retry_at = record.get("next_retry_at")
        if not next_retry_at:
            continue
        if datetime.fromisoformat(str(next_retry_at)) <= now:
            due_records.append(record)
    due_records = sorted(due_records, key=lambda item: item.get("next_retry_at"))[: max(int(retry_limit), 1)]

    if not due_records:
        print("ℹ️ 当前没有到期的飞书补发任务")
        return 0

    print(f"🔁 本轮处理 {len(due_records)} 条飞书补发任务")
    for record in due_records:
        attempt_number = int(record.get("attempts_made", 0)) + 1
        command = build_retry_command(settings, record)
        try:
            proc = subprocess.run(command, capture_output=True, text=True, timeout=180)
            output = ((proc.stdout or "") + (proc.stderr or "")).strip()
            return_code = proc.returncode
        except subprocess.TimeoutExpired:
            output = "retry worker timeout"
            return_code = 1

        record["updated_at"] = iso_now()
        record["attempts_made"] = attempt_number
        record["last_output"] = output[-2000:]
        if return_code == 0:
            record["status"] = "delivered"
            record["delivered_at"] = iso_now()
            write_retry_audit(settings, "delivered", record=record, detail=f"第 {attempt_number} 次尝试成功")
            continue

        retryable = is_retryable_error(detail=output)
        next_retry_at = next_retry_at_for_attempt(attempt_number)
        if retryable and attempt_number < int(record.get("max_attempts", RETRY_MAX_ATTEMPTS)) and next_retry_at:
            record["status"] = "pending"
            record["next_retry_at"] = next_retry_at
            write_retry_audit(settings, "rescheduled", record=record, detail=f"第 {attempt_number} 次尝试失败，已安排下次补发")
            continue

        record["status"] = "failed"
        record["failed_at"] = iso_now()
        record["next_retry_at"] = None
        reason = "达到最大尝试次数" if retryable else "错误不可重试"
        write_retry_audit(settings, "failed", record=record, detail=f"第 {attempt_number} 次尝试失败，{reason}")
        print(f"❌ 补发最终失败：{record['id']}（{reason}）")

    save_retry_queue(settings, queue)
    return 0


def validate_template_payload(template_name: str, data: dict[str, Any], template_config: dict[str, Any]) -> None:
    required_fields = template_config.get("required_fields") or []
    missing = [field for field in required_fields if field not in data]
    if missing:
        raise ValueError(f"模板 {template_name} 缺少字段: {', '.join(missing)}")


def send_template_message(settings: AppSettings, args: argparse.Namespace) -> int:
    if not args.template or not args.data:
        raise ValueError("template 模式必须提供 --template 和 --data")

    registry = load_template_registry(settings)
    template_config = get_template_config(registry, args.template)
    data = json.loads(args.data)
    validate_template_payload(args.template, data, template_config)
    validate_known_job_id(settings, args.job_id, Path(args.jobs_file) if args.jobs_file else None, args.agent_id)

    route = resolve_route(
        template_config,
        cli_overrides={
            "target_id": args.target_id,
            "target_type": args.target_type,
            "delivery_channel": args.delivery_channel,
        },
    )
    thread_options = resolve_thread_options(args, args.template, template_config, route, data)
    app_id, app_secret = load_account_credentials(settings, args.agent_id)
    access_token = get_tenant_access_token(app_id, app_secret)

    print(f"📨 路由解析：channel={route['delivery']['channel']} target={route['target']['type']}:{route['target']['id']}")
    if thread_options:
        print(f"🧵 固定话题：key={thread_options['binding_key']} title={thread_options['title']}")

    card = build_generic_card(args.template, template_config, data)
    result = dispatch_message(settings, access_token, route, "interactive", card, thread_options)
    success = result["ok"]
    response_meta = result["result"]
    if success and thread_options:
        summary_result = maybe_send_thread_summary_reply(settings, access_token, thread_options, response_meta, data)
        if summary_result:
            write_send_audit(settings, "success" if summary_result["ok"] else "failed", args.agent_id, "thread-summary-reply", route=route, template_name=f"{args.template}#summary", response_meta=summary_result["result"])

    if not success:
        enqueue_retry(settings, args, args.agent_id, args.template, route=route, response_meta=response_meta)

    write_send_audit(settings, "success" if success else "failed", args.agent_id, "template", route=route, template_name=args.template, response_meta=response_meta)
    return 0 if success else 1


def send_text_message(settings: AppSettings, args: argparse.Namespace) -> int:
    if not args.content:
        raise ValueError("text 模式必须提供 --content")
    route = {
        "target": {"id": args.target_id, "type": args.target_type},
        "delivery": {"channel": args.delivery_channel},
        "policy": {"lock_target": False, "lock_delivery": False},
        "thread": {"enabled": False, "summary_reply": {"enabled": False}},
    }
    route = normalize_route_config(route)
    app_id, app_secret = load_account_credentials(settings, args.agent_id)
    access_token = get_tenant_access_token(app_id, app_secret)
    result = dispatch_message(settings, access_token, route, "text", {"text": args.content})
    if not result["ok"]:
        enqueue_retry(settings, args, args.agent_id, None, route=route, response_meta=result["result"])
    write_send_audit(settings, "success" if result["ok"] else "failed", args.agent_id, "text", route=route, response_meta=result["result"])
    return 0 if result["ok"] else 1


def build_settings_from_args(args: argparse.Namespace, entry_script: Path) -> AppSettings:
    project_root = entry_script.resolve().parents[1]
    templates_file = Path(args.templates_file) if args.templates_file else project_root / "examples" / "feishu-templates.example.json"
    jobs_file = Path(args.jobs_file) if args.jobs_file else project_root / "examples" / "jobs.example.json"
    accounts_file = Path(args.accounts_file) if args.accounts_file else project_root / "examples" / "accounts.example.json"
    state_dir = Path(args.state_dir) if args.state_dir else project_root / "state"
    logs_dir = Path(args.logs_dir) if args.logs_dir else project_root / "logs"
    return AppSettings(
        project_root=project_root,
        templates_file=templates_file,
        jobs_file=jobs_file,
        accounts_file=accounts_file,
        state_dir=state_dir,
        logs_dir=logs_dir,
        entry_script=entry_script,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OpenClaw Feishu Cron Kit")
    parser.add_argument("--mode", choices=["template", "text", "retry-pending"], default="template")
    parser.add_argument("--template")
    parser.add_argument("--data")
    parser.add_argument("--content")
    parser.add_argument("--agent-id", default="default")
    parser.add_argument("--target-id")
    parser.add_argument("--target-type")
    parser.add_argument("--delivery-channel")
    parser.add_argument("--job-id")
    parser.add_argument("--jobs-file")
    parser.add_argument("--templates-file")
    parser.add_argument("--accounts-file")
    parser.add_argument("--state-dir")
    parser.add_argument("--logs-dir")
    parser.add_argument("--thread-mode", choices=sorted(THREAD_MODES), default="auto")
    parser.add_argument("--thread-key")
    parser.add_argument("--thread-title")
    parser.add_argument("--disable-retry-queue", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--retry-limit", type=int, default=10, help=argparse.SUPPRESS)
    return parser


def run_cli(argv: list[str] | None = None, entry_script: Path | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = build_settings_from_args(args, entry_script or Path(__file__).resolve())
    try:
        if args.mode == "retry-pending":
            return process_retry_queue(settings, retry_limit=args.retry_limit)
        if args.mode == "template":
            return send_template_message(settings, args)
        return send_text_message(settings, args)
    except KeyboardInterrupt:
        print("⛔ 已取消执行")
        return 130
    except Exception as exc:
        print(f"❌ 执行失败: {exc}")
        return 1
