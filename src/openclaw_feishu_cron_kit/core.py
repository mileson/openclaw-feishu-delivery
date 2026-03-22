from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import requests

from .renderer import build_generic_card, build_summary_post, build_summary_text
from .storage import append_jsonl, load_json_file, save_json_file
from .template_normalizers import normalize_template_data

DELIVERY_CHANNELS = {"direct", "message", "topic"}
USER_TARGET_TYPES = {"open_id", "union_id", "user_id", "email"}
GROUP_TARGET_TYPES = {"chat_id"}
THREAD_MODES = {"auto", "off", "new", "reply"}
SUPPORTED_TRANSPORT_PROVIDERS = {"feishu"}
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
_TEMPLATE_TOKEN_RE = re.compile(r"\{([^{}]+)\}")


@dataclass
class AppSettings:
    project_root: Path
    runtime_dir: Path
    templates_file: Path
    jobs_file: Path | None
    accounts_file: Path | None
    openclaw_config_file: Path | None
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


def resolve_runtime_file(
    cli_value: str | Path | None,
    runtime_dir: Path,
    runtime_filename: str,
    fallback_path: Path | None,
) -> Path | None:
    if cli_value:
        return Path(cli_value)

    runtime_path = runtime_dir / runtime_filename
    if runtime_path.exists():
        return runtime_path

    return fallback_path


def build_settings(
    *,
    project_root: Path,
    entry_script: Path | None = None,
    templates_file: str | Path | None = None,
    jobs_file: str | Path | None = None,
    accounts_file: str | Path | None = None,
    openclaw_config_file: str | Path | None = None,
    state_dir: str | Path | None = None,
    logs_dir: str | Path | None = None,
) -> AppSettings:
    project_root = Path(project_root).resolve()
    runtime_dir = project_root / "runtime"
    entry_script = Path(entry_script).resolve() if entry_script else (project_root / "scripts" / "send_message.py").resolve()
    templates_path = resolve_runtime_file(
        templates_file,
        runtime_dir,
        "feishu-templates.local.json",
        project_root / "examples" / "feishu-templates.example.json",
    )
    jobs_path = Path(jobs_file) if jobs_file else project_root / "examples" / "jobs.example.json"
    accounts_path = resolve_runtime_file(
        accounts_file,
        runtime_dir,
        "accounts.local.json",
        project_root / "examples" / "accounts.example.json",
    )
    openclaw_config_path = Path(openclaw_config_file) if openclaw_config_file else None
    if not openclaw_config_path:
        env_openclaw_config = os.environ.get("OPENCLAW_CONFIG")
        if env_openclaw_config:
            openclaw_config_path = Path(env_openclaw_config)
        else:
            candidate = Path.home() / ".openclaw" / "openclaw.json"
            if candidate.exists():
                openclaw_config_path = candidate
    resolved_state_dir = Path(state_dir) if state_dir else project_root / "state"
    resolved_logs_dir = Path(logs_dir) if logs_dir else project_root / "logs"
    return AppSettings(
        project_root=project_root,
        runtime_dir=runtime_dir,
        templates_file=templates_path,
        jobs_file=jobs_path,
        accounts_file=accounts_path,
        openclaw_config_file=openclaw_config_path,
        state_dir=resolved_state_dir,
        logs_dir=resolved_logs_dir,
        entry_script=entry_script,
    )


def extract_app_credentials(account: dict[str, Any] | None) -> tuple[str, str] | None:
    if not isinstance(account, dict):
        return None

    app_id = str(account.get("app_id") or account.get("appId") or "").strip()
    app_secret = str(account.get("app_secret") or account.get("appSecret") or "").strip()
    if app_id and app_secret:
        return app_id, app_secret
    return None


def load_openclaw_account_registry(config_path: Path | None) -> dict[str, Any] | None:
    if not config_path or not config_path.exists():
        return None

    data = json.loads(config_path.read_text(encoding="utf-8"))
    accounts = ((data.get("channels") or {}).get("feishu") or {}).get("accounts") or {}
    if isinstance(accounts, dict):
        return accounts
    return None


def load_template_registry(settings: AppSettings) -> dict[str, Any]:
    return json.loads(settings.templates_file.read_text(encoding="utf-8"))


def get_template_config(registry: dict[str, Any], template_name: str) -> dict[str, Any]:
    templates = registry.get("templates", registry)
    template = templates.get(template_name)
    if not template:
        raise ValueError(f"未知模板: {template_name}")
    return deepcopy(template)


def normalize_route_config(raw_value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw_value, dict):
        raise ValueError(f"无效 route 配置: {raw_value}")
    target = raw_value.get("target") or {}
    delivery = raw_value.get("delivery") or {}
    policy = raw_value.get("policy") or {}
    thread = raw_value.get("thread") or {}
    transport = raw_value.get("transport") or {}

    target_type = target.get("type")
    if target_type not in USER_TARGET_TYPES | GROUP_TARGET_TYPES:
        raise ValueError(f"无效 target.type: {target_type}")
    provider = str(transport.get("provider") or "feishu").strip().lower() or "feishu"
    if provider not in SUPPORTED_TRANSPORT_PROVIDERS:
        raise ValueError(f"当前暂不支持 transport.provider={provider}")
    channel = delivery.get("channel")
    if channel not in DELIVERY_CHANNELS:
        raise ValueError(f"无效 delivery.channel: {channel}")
    if channel == "direct" and target_type not in USER_TARGET_TYPES:
        raise ValueError("direct 通道只允许私聊目标")
    if channel in {"message", "topic"} and target_type not in GROUP_TARGET_TYPES:
        raise ValueError("message/topic 通道只允许群目标")

    return {
        "transport": {
            "provider": provider,
            "account": str(transport.get("account") or "").strip(),
        },
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

    if cli_overrides.get("transport_provider"):
        route["transport"]["provider"] = cli_overrides["transport_provider"]
    if cli_overrides.get("transport_account"):
        route["transport"]["account"] = cli_overrides["transport_account"]

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


def _resolve_template_value(payload: Any, path: str) -> Any:
    current = payload
    for chunk in path.split("."):
        key = chunk.strip()
        if not key or not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _render_data_template(template: str, data: dict[str, Any]) -> str:
    raw_template = str(template or "").strip()
    if not raw_template:
        return ""

    def replace(match: re.Match[str]) -> str:
        token = match.group(1).strip()
        value = _resolve_template_value(data, token)
        if value is None:
            return ""
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        return str(value).strip()

    return _TEMPLATE_TOKEN_RE.sub(replace, raw_template).strip()


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

    binding_key_template = str(thread_config.get("binding_key_template") or "").strip()
    rendered_binding_key = _render_data_template(binding_key_template, data) if binding_key_template else ""
    title_template = str(thread_config.get("title_template") or "").strip()
    rendered_title = _render_data_template(title_template, data) if title_template else ""

    binding_key = args.thread_key or rendered_binding_key or (f"job:{args.job_id}" if args.job_id else build_default_thread_key(args.agent_id or "default", template_name, route["target"]["id"]))
    title = args.thread_title or rendered_title or data.get("title") or template_config.get("description") or template_name
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
        payload["transport_provider"] = route["transport"]["provider"]
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


def load_account_credentials(settings: AppSettings, agent_id: str | None, account_name: str | None = None) -> tuple[str, str]:
    env_app_id = os.environ.get("FEISHU_APP_ID")
    env_app_secret = os.environ.get("FEISHU_APP_SECRET")
    if env_app_id and env_app_secret:
        return env_app_id, env_app_secret

    if settings.accounts_file and settings.accounts_file.exists():
        data = json.loads(settings.accounts_file.read_text(encoding="utf-8"))
        accounts = data.get("accounts", data)
        if account_name and account_name in accounts:
            account = accounts[account_name]
        elif agent_id and agent_id in accounts:
            account = accounts[agent_id]
        else:
            account = accounts.get("default") or accounts.get("main")
        credentials = extract_app_credentials(account)
        if credentials:
            return credentials

    openclaw_accounts = load_openclaw_account_registry(settings.openclaw_config_file)
    if openclaw_accounts:
        if account_name and account_name in openclaw_accounts:
            credentials = extract_app_credentials(openclaw_accounts.get(account_name))
            if credentials:
                return credentials

        if agent_id and agent_id in openclaw_accounts:
            credentials = extract_app_credentials(openclaw_accounts.get(agent_id))
            if credentials:
                return credentials

        for fallback_key in ("default", "main"):
            credentials = extract_app_credentials(openclaw_accounts.get(fallback_key))
            if credentials:
                return credentials

    raise ValueError("未提供飞书凭证，请配置 FEISHU_APP_ID / FEISHU_APP_SECRET，提供 accounts 文件，或提供 OpenClaw openclaw.json")


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


def resolve_access_token(settings: AppSettings, agent_id: str | None, account_name: str | None = None) -> str:
    app_id, app_secret = load_account_credentials(settings, agent_id, account_name=account_name)
    return get_tenant_access_token(app_id, app_secret)


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


def pin_message_request(access_token: str, message_id: str, label: str = "消息置顶") -> dict[str, Any]:
    url = "https://open.feishu.cn/open-apis/im/v1/pins"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    payload = {"message_id": message_id}
    return execute_feishu_request(url, headers, payload, label)


def unpin_message_request(access_token: str, message_id: str, label: str = "取消消息置顶") -> dict[str, Any]:
    url = f"https://open.feishu.cn/open-apis/im/v1/pins/{message_id}"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    try:
        response = requests.delete(url, headers=headers, timeout=30)
    except requests.RequestException as exc:
        result = {"code": -1, "msg": f"request_error: {exc}", "raw": str(exc)}
        print(f"❌ {label}失败: {result}")
        return {"ok": False, "result": result}

    result = parse_response_json(response)
    if result.get("code") == 0:
        print(f"✅ {label}成功")
        return {"ok": True, "result": result}
    print(f"❌ {label}失败: {result}")
    return {"ok": False, "result": result}


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
    provider = route["transport"]["provider"]
    if provider != "feishu":
        raise ValueError(f"当前尚未实现 transport.provider={provider} 的发送器")
    channel = route["delivery"]["channel"]
    if channel == "direct":
        return post_message_request(access_token, route, msg_type, content_payload, "私聊消息")
    if channel == "message":
        return post_message_request(access_token, route, msg_type, content_payload, "群普通消息")
    if channel == "topic":
        return dispatch_topic_message(settings, access_token, route, msg_type, content_payload, thread_options)
    raise ValueError(f"未知 delivery.channel: {channel}")


def extract_thread_followups(data: dict[str, Any]) -> list[dict[str, Any]]:
    raw_followups = data.get("thread_followups") or []
    if not raw_followups:
        return []
    if not isinstance(raw_followups, list):
        raise ValueError("thread_followups 必须是数组")

    followups: list[dict[str, Any]] = []
    for raw_item in raw_followups:
        if not isinstance(raw_item, dict):
            raise ValueError("thread_followups 的每一项都必须是对象")
        template_name = str(raw_item.get("template_name") or "").strip()
        followup_data = raw_item.get("data")
        if not template_name:
            raise ValueError("thread_followups.template_name 不能为空")
        if not isinstance(followup_data, dict):
            raise ValueError("thread_followups.data 必须是对象")
        followups.append(
            {
                "template_name": template_name,
                "required": bool(raw_item.get("required", True)),
                "data": followup_data,
            }
        )
    return followups


def maybe_send_thread_followup_cards(
    settings: AppSettings,
    registry: dict[str, Any],
    access_token: str,
    route: dict[str, Any],
    thread_options: dict[str, Any] | None,
    data: dict[str, Any],
) -> list[dict[str, Any]]:
    if not thread_options:
        return []

    followups = extract_thread_followups(data)
    results: list[dict[str, Any]] = []
    for followup in followups:
        followup_template = followup["template_name"]
        template_config = get_template_config(registry, followup_template)
        followup_data = normalize_template_data(followup_template, followup["data"])
        validate_template_payload(followup_template, followup_data, template_config)
        card = build_generic_card(followup_template, template_config, followup_data)
        result = dispatch_message(settings, access_token, route, "interactive", card, thread_options)
        results.append(
            {
                "template_name": followup_template,
                "required": bool(followup["required"]),
                "ok": bool(result["ok"]),
                "result": result["result"],
                "message_id": extract_message_id(result["result"]),
            }
        )
        if not result["ok"] and followup["required"]:
            break
    return results


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
    summary_channel = str(((thread_options or {}).get("summary_reply") or {}).get("channel") or "post").strip().lower() or "post"
    if summary_channel == "text":
        content = build_summary_text(summary_data)
        return reply_message_request(access_token, root_message_id, "text", content, "群话题摘要回复")

    content = build_summary_post(thread_options["title"], summary_data)
    result = reply_message_request(access_token, root_message_id, "post", content, "群话题摘要回复")
    if result["ok"] or not is_invalid_message_content(result["result"]):
        return result

    print("⚠️ 群话题摘要回复 post 内容被拒绝，降级为 text 重试")
    fallback_content = build_summary_text(summary_data)
    return reply_message_request(access_token, root_message_id, "text", fallback_content, "群话题摘要回复(text)")


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


def is_invalid_message_content(result_meta: dict[str, Any] | None = None) -> bool:
    if not result_meta:
        return False
    if result_meta.get("code") == 230001:
        return True
    return "invalid message content" in extract_error_text(result_meta=result_meta)


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


def _build_template_retry_args(
    settings: AppSettings,
    *,
    template_name: str,
    data: dict[str, Any],
    agent_id: str,
    job_id: str | None,
    jobs_file: Path | None,
    target_id: str | None,
    target_type: str | None,
    delivery_channel: str | None,
    transport_provider: str | None,
    transport_account: str | None,
    thread_mode: str,
    thread_key: str | None,
    thread_title: str | None,
    disable_retry_queue: bool,
) -> argparse.Namespace:
    return argparse.Namespace(
        mode="template",
        template=template_name,
        data=json.dumps(data, ensure_ascii=False),
        content=None,
        agent_id=agent_id,
        target_id=target_id,
        target_type=target_type,
        delivery_channel=delivery_channel,
        transport_provider=transport_provider,
        transport_account=transport_account,
        job_id=job_id,
        jobs_file=str(jobs_file) if jobs_file else None,
        thread_mode=thread_mode,
        thread_key=thread_key,
        thread_title=thread_title,
        templates_file=str(settings.templates_file) if settings.templates_file else None,
        accounts_file=str(settings.accounts_file) if settings.accounts_file else None,
        state_dir=str(settings.state_dir),
        logs_dir=str(settings.logs_dir),
        disable_retry_queue=disable_retry_queue,
    )


def send_template_payload(
    settings: AppSettings,
    *,
    template_name: str,
    data: dict[str, Any],
    agent_id: str,
    job_id: str | None = None,
    jobs_file: Path | None = None,
    target_id: str | None = None,
    target_type: str | None = None,
    delivery_channel: str | None = None,
    transport_provider: str | None = None,
    transport_account: str | None = None,
    thread_mode: str = "auto",
    thread_key: str | None = None,
    thread_title: str | None = None,
    disable_retry_queue: bool = False,
) -> dict[str, Any]:
    registry = load_template_registry(settings)
    template_config = get_template_config(registry, template_name)
    data = normalize_template_data(template_name, data)
    validate_template_payload(template_name, data, template_config)
    resolved_jobs_file = jobs_file or settings.jobs_file
    validate_known_job_id(settings, job_id, resolved_jobs_file, agent_id)

    route = resolve_route(
        template_config,
        cli_overrides={
            "target_id": target_id,
            "target_type": target_type,
            "delivery_channel": delivery_channel,
            "transport_provider": transport_provider,
            "transport_account": transport_account,
        },
    )
    runtime_args = _build_template_retry_args(
        settings,
        template_name=template_name,
        data=data,
        agent_id=agent_id,
        job_id=job_id,
        jobs_file=resolved_jobs_file,
        target_id=target_id,
        target_type=target_type,
        delivery_channel=delivery_channel,
        transport_provider=transport_provider,
        transport_account=transport_account,
        thread_mode=thread_mode,
        thread_key=thread_key,
        thread_title=thread_title,
        disable_retry_queue=disable_retry_queue,
    )
    thread_options = resolve_thread_options(runtime_args, template_name, template_config, route, data)
    access_token = resolve_access_token(settings, agent_id, account_name=route["transport"]["account"] or None)

    print(
        "📨 路由解析："
        f"provider={route['transport']['provider']} "
        f"channel={route['delivery']['channel']} "
        f"target={route['target']['type']}:{route['target']['id']}"
    )
    if thread_options:
        print(f"🧵 固定话题：key={thread_options['binding_key']} title={thread_options['title']}")

    card = build_generic_card(template_name, template_config, data)
    result = dispatch_message(settings, access_token, route, "interactive", card, thread_options)
    success = result["ok"]
    response_meta = result["result"]
    followup_results: list[dict[str, Any]] = []
    summary_result: dict[str, Any] | None = None
    if success and thread_options:
        followup_results = maybe_send_thread_followup_cards(settings, registry, access_token, route, thread_options, data)
        for followup_result in followup_results:
            write_send_audit(
                settings,
                "success" if followup_result["ok"] else "failed",
                agent_id,
                "thread-followup",
                route=route,
                template_name=followup_result["template_name"],
                response_meta=followup_result["result"],
            )
            if not followup_result["ok"] and followup_result["required"]:
                response_meta = followup_result["result"]
                success = False
                break

        if success:
            summary_result = maybe_send_thread_summary_reply(settings, access_token, thread_options, response_meta, data)
            if summary_result:
                write_send_audit(
                    settings,
                    "success" if summary_result["ok"] else "failed",
                    agent_id,
                    "thread-summary-reply",
                    route=route,
                    template_name=f"{template_name}#summary",
                    response_meta=summary_result["result"],
                )
                summary_required = bool((((thread_options or {}).get("summary_reply")) or {}).get("required"))
                if summary_required and not summary_result["ok"]:
                    success = False
                    response_meta = summary_result["result"]

    if not success:
        enqueue_retry(settings, runtime_args, agent_id, template_name, route=route, response_meta=response_meta)

    write_send_audit(settings, "success" if success else "failed", agent_id, "template", route=route, template_name=template_name, response_meta=response_meta)
    return {
        "ok": success,
        "route": route,
        "thread_options": thread_options,
        "result": response_meta,
        "followup_results": followup_results,
        "summary_result": summary_result,
        "message_id": extract_message_id(response_meta),
    }


def send_template_message(settings: AppSettings, args: argparse.Namespace) -> int:
    if not args.template or not args.data:
        raise ValueError("template 模式必须提供 --template 和 --data")
    data = json.loads(args.data)
    outcome = send_template_payload(
        settings,
        template_name=args.template,
        data=data,
        agent_id=args.agent_id,
        job_id=args.job_id,
        jobs_file=Path(args.jobs_file) if args.jobs_file else None,
        target_id=args.target_id,
        target_type=args.target_type,
        delivery_channel=args.delivery_channel,
        transport_provider=args.transport_provider,
        transport_account=args.transport_account,
        thread_mode=args.thread_mode,
        thread_key=args.thread_key,
        thread_title=args.thread_title,
        disable_retry_queue=bool(args.disable_retry_queue),
    )
    return 0 if outcome["ok"] else 1


def send_text_message(settings: AppSettings, args: argparse.Namespace) -> int:
    if not args.content:
        raise ValueError("text 模式必须提供 --content")
    route = {
        "transport": {"provider": args.transport_provider or "feishu", "account": args.transport_account or args.agent_id},
        "target": {"id": args.target_id, "type": args.target_type},
        "delivery": {"channel": args.delivery_channel},
        "policy": {"lock_target": False, "lock_delivery": False},
        "thread": {"enabled": False, "summary_reply": {"enabled": False}},
    }
    route = normalize_route_config(route)
    app_id, app_secret = load_account_credentials(settings, args.agent_id, account_name=route["transport"]["account"] or None)
    access_token = get_tenant_access_token(app_id, app_secret)
    result = dispatch_message(settings, access_token, route, "text", {"text": args.content})
    if not result["ok"]:
        enqueue_retry(settings, args, args.agent_id, None, route=route, response_meta=result["result"])
    write_send_audit(settings, "success" if result["ok"] else "failed", args.agent_id, "text", route=route, response_meta=result["result"])
    return 0 if result["ok"] else 1


def build_settings_from_args(args: argparse.Namespace, entry_script: Path) -> AppSettings:
    return build_settings(
        project_root=entry_script.resolve().parents[1],
        entry_script=entry_script,
        templates_file=args.templates_file,
        jobs_file=args.jobs_file,
        accounts_file=args.accounts_file,
        openclaw_config_file=args.openclaw_config_file,
        state_dir=args.state_dir,
        logs_dir=args.logs_dir,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OpenClaw Feishu Delivery")
    parser.add_argument("--mode", choices=["template", "text", "retry-pending"], default="template")
    parser.add_argument("--template")
    parser.add_argument("--data")
    parser.add_argument("--content")
    parser.add_argument("--agent-id", default="default")
    parser.add_argument("--target-id")
    parser.add_argument("--target-type")
    parser.add_argument("--delivery-channel")
    parser.add_argument("--transport-provider")
    parser.add_argument("--transport-account")
    parser.add_argument("--job-id")
    parser.add_argument("--jobs-file")
    parser.add_argument("--templates-file")
    parser.add_argument("--accounts-file")
    parser.add_argument("--openclaw-config-file")
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
