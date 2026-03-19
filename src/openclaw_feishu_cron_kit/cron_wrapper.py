from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .core import AppSettings, iso_now, send_template_payload
from .storage import append_jsonl, load_json_file, save_json_file

PAYLOAD_START = "OPENCLAW_TEMPLATE_PAYLOAD_START"
PAYLOAD_END = "OPENCLAW_TEMPLATE_PAYLOAD_END"
PAYLOAD_FILE = "OPENCLAW_TEMPLATE_PAYLOAD_FILE"


class PayloadExtractionError(ValueError):
    """Raised when a cron summary does not contain a valid payload block."""


def wrapper_state_file(settings: AppSettings) -> Path:
    return settings.state_dir / "cron-wrapper-deliveries.json"


def wrapper_audit_log(settings: AppSettings) -> Path:
    return settings.logs_dir / "cron-wrapper-audit.jsonl"


def load_wrapper_state(settings: AppSettings) -> dict[str, Any]:
    payload = load_json_file(wrapper_state_file(settings), {"version": 1, "jobs": {}})
    if not isinstance(payload, dict):
        payload = {"version": 1, "jobs": {}}
    if not isinstance(payload.get("jobs"), dict):
        payload["jobs"] = {}
    return payload


def save_wrapper_state(settings: AppSettings, payload: dict[str, Any]) -> None:
    save_json_file(wrapper_state_file(settings), payload)


def write_wrapper_audit(
    settings: AppSettings,
    *,
    action: str,
    job_id: str,
    template_name: str | None = None,
    run_at_ms: int | None = None,
    detail: str | None = None,
    response_meta: dict[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {
        "timestamp": iso_now(),
        "action": action,
        "job_id": job_id,
    }
    if template_name:
        payload["template"] = template_name
    if run_at_ms is not None:
        payload["run_at_ms"] = run_at_ms
    if detail:
        payload["detail"] = detail
    if response_meta:
        payload["response"] = response_meta
    append_jsonl(wrapper_audit_log(settings), payload)


def load_delivery_config(config_path: Path) -> dict[str, Any]:
    payload = load_json_file(config_path, {"version": 1, "jobs": []})
    if not isinstance(payload, dict):
        raise ValueError("cron wrapper 配置必须是对象")
    jobs = payload.get("jobs")
    if not isinstance(jobs, list):
        raise ValueError("cron wrapper 配置中的 jobs 必须是数组")
    normalized_jobs: list[dict[str, Any]] = []
    for item in jobs:
        if not isinstance(item, dict):
            raise ValueError("cron wrapper 每个 job 配置都必须是对象")
        job_id = str(item.get("job_id") or "").strip()
        template_name = str(item.get("template") or "").strip()
        agent_id = str(item.get("agent_id") or "").strip()
        if not job_id or not template_name or not agent_id:
            raise ValueError("cron wrapper job 配置必须包含 job_id/template/agent_id")
        normalized_jobs.append(
            {
                "job_id": job_id,
                "template": template_name,
                "agent_id": agent_id,
                "jobs_file": item.get("jobs_file"),
                "runs_dir": item.get("runs_dir"),
            }
        )
    return {"version": payload.get("version") or 1, "jobs": normalized_jobs}


def _load_payload_file(path: Path) -> dict[str, Any]:
    if not path.is_absolute():
        raise PayloadExtractionError("payload 文件路径必须是绝对路径")
    if not path.exists():
        raise PayloadExtractionError(f"payload 文件不存在: {path}")
    payload = load_json_file(path, None)
    if not isinstance(payload, dict):
        raise PayloadExtractionError("payload 文件内容必须是 JSON 对象")
    return payload


def _extract_balanced_json_object(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "{":
            depth += 1
            continue
        if char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def extract_payload_block(summary: str) -> dict[str, Any]:
    text = (summary or "").strip()
    if not text:
        raise PayloadExtractionError("cron summary 为空")

    file_pattern = re.compile(rf"{PAYLOAD_FILE}\s*[:：]?\s*`?([^\n`]+)`?")
    file_match = file_pattern.search(text)
    if file_match:
        payload_path = Path(file_match.group(1).strip())
        return _load_payload_file(payload_path)

    pattern = re.compile(
        rf"{PAYLOAD_START}\s*(?:```json)?\s*(\{{.*?\}})\s*(?:```)?\s*{PAYLOAD_END}",
        re.S,
    )
    match = pattern.search(text)
    if match:
        candidate = match.group(1)
    elif PAYLOAD_START in text:
        start_index = text.index(PAYLOAD_START) + len(PAYLOAD_START)
        candidate = _extract_balanced_json_object(text[start_index:]) or text
    else:
        candidate = text
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise PayloadExtractionError("未找到有效的 payload JSON block") from exc
    if not isinstance(payload, dict):
        raise PayloadExtractionError("payload 必须是 JSON 对象")
    return payload


def load_latest_finished_run(runs_dir: Path, job_id: str) -> dict[str, Any] | None:
    path = runs_dir / f"{job_id}.jsonl"
    if not path.exists():
        return None
    latest: dict[str, Any] | None = None
    latest_run_at = -1
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if payload.get("action") != "finished":
            continue
        run_at_ms = int(payload.get("runAtMs") or 0)
        if run_at_ms >= latest_run_at:
            latest = payload
            latest_run_at = run_at_ms
    return latest


def _normalize_optional_path(value: Any) -> Path | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    return Path(raw)


def deliver_configured_jobs(
    settings: AppSettings,
    *,
    config_path: Path,
    only_job_id: str | None = None,
    default_runs_dir: Path | None = None,
) -> list[dict[str, Any]]:
    config = load_delivery_config(config_path)
    state = load_wrapper_state(settings)
    state_jobs = state["jobs"]
    results: list[dict[str, Any]] = []
    runs_root = default_runs_dir or Path("/root/.openclaw/cron/runs")

    for job in config["jobs"]:
        job_id = job["job_id"]
        if only_job_id and job_id != only_job_id:
            continue
        template_name = job["template"]
        agent_id = job["agent_id"]
        runs_dir = _normalize_optional_path(job.get("runs_dir")) or runs_root
        latest = load_latest_finished_run(runs_dir, job_id)
        if not latest:
            results.append({"job_id": job_id, "status": "missing-run"})
            write_wrapper_audit(settings, action="missing-run", job_id=job_id, template_name=template_name, detail=f"runs_dir={runs_dir}")
            continue

        run_at_ms = int(latest.get("runAtMs") or 0)
        delivered = state_jobs.get(job_id) or {}
        if int(delivered.get("run_at_ms") or 0) >= run_at_ms:
            results.append({"job_id": job_id, "status": "already-delivered", "run_at_ms": run_at_ms})
            continue

        try:
            data = extract_payload_block(str(latest.get("summary") or ""))
        except PayloadExtractionError as exc:
            results.append({"job_id": job_id, "status": "missing-payload", "run_at_ms": run_at_ms, "detail": str(exc)})
            write_wrapper_audit(settings, action="missing-payload", job_id=job_id, template_name=template_name, run_at_ms=run_at_ms, detail=str(exc))
            continue

        outcome = send_template_payload(
            settings,
            template_name=template_name,
            data=data,
            agent_id=agent_id,
            job_id=job_id,
            jobs_file=_normalize_optional_path(job.get("jobs_file")) or settings.jobs_file,
        )
        if outcome["ok"]:
            state_jobs[job_id] = {
                "run_at_ms": run_at_ms,
                "template": template_name,
                "message_id": outcome.get("message_id"),
                "delivered_at": datetime.now().isoformat(timespec="seconds"),
            }
            save_wrapper_state(settings, state)
            write_wrapper_audit(
                settings,
                action="delivered",
                job_id=job_id,
                template_name=template_name,
                run_at_ms=run_at_ms,
                response_meta=outcome.get("result"),
            )
            results.append({"job_id": job_id, "status": "delivered", "run_at_ms": run_at_ms, "message_id": outcome.get("message_id")})
            continue

        write_wrapper_audit(
            settings,
            action="send-failed",
            job_id=job_id,
            template_name=template_name,
            run_at_ms=run_at_ms,
            response_meta=outcome.get("result"),
        )
        results.append({"job_id": job_id, "status": "send-failed", "run_at_ms": run_at_ms})

    return results
