from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from .core import build_settings, parse_response_json, resolve_access_token
from .template_normalizers import normalize_template_data


BITABLE_FIELD_NAMES = [
    "选题标题",
    "topic_uid",
    "SCORE",
    "优先级",
    "来源Agent",
    "来源任务",
    "发现时间",
    "X确认状态",
    "来源说明",
    "X参考链接",
    "核心要点",
    "内容角度",
    "适合平台",
    "发布状态",
    "原始摘要",
    "创建时间",
]


@dataclass
class CandidateRecord:
    title: str
    topic_phrase: str
    topic_uid: str
    score: int
    priority: str
    discovered_at_ms: int
    discovered_day: str
    x_confirm_status: str
    source_note: str
    x_reference_url: str
    core_points: str
    content_angle: str
    platforms: list[str]
    raw_summary: str
    emoji: str


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Upsert AI hotspot candidates into Feishu Bitable and materialize a delivery payload.")
    parser.add_argument("--input", required=True, help="Path to the raw hotspot candidate JSON file.")
    parser.add_argument("--output", required=True, help="Path to the final delivery payload JSON file.")
    parser.add_argument("--bitable-config", required=True, help="Path to topic-backlog-bitable.json.")
    parser.add_argument("--project-root", help="openclaw-feishu-delivery project root. Defaults to the script parent.")
    parser.add_argument("--agent-id", default="blogger")
    parser.add_argument("--task-name", default="ai-hotspot")
    return parser.parse_args(argv)


def build_topic_uid(title: str, discovered_day: str, agent_id: str) -> str:
    slug = _slugify_topic_phrase(derive_topic_phrase(title))
    return f"sha1-{slug}-{discovered_day}-{agent_id}"


def select_upsert_target(records: list[dict[str, Any]], discovered_day: str, canonical_uid: str) -> tuple[dict[str, Any] | None, int]:
    if not records:
        return None, 0

    canonical_matches = [record for record in records if _field_text(record, "topic_uid") == canonical_uid]
    if canonical_matches:
        canonical_matches.sort(key=lambda record: int(record.get("created_time") or 0))
        return canonical_matches[0], max(0, len(canonical_matches) - 1)

    day_matches = []
    for record in records:
        created_day = _field_day(record, "发现时间")
        if created_day == discovered_day:
            day_matches.append(record)
    if not day_matches:
        return None, 0
    day_matches.sort(key=lambda record: int(record.get("created_time") or 0))
    return day_matches[0], max(0, len(day_matches) - 1)


def normalize_candidate(item: dict[str, Any], *, scan_time_text: str, agent_id: str, task_name: str) -> CandidateRecord:
    title = str(item.get("title") or "").strip()
    if not title:
        raise ValueError("候选项缺少 title")

    score = _coerce_int(item.get("score"))
    if score < 18:
        raise ValueError(f"候选项 SCORE 不满足入库门槛: {title}")

    discovered_at_ms = _parse_datetime_ms(item.get("discovered_at") or item.get("发现时间") or scan_time_text)
    discovered_day = datetime.fromtimestamp(discovered_at_ms / 1000).strftime("%Y-%m-%d")
    topic_phrase = str(item.get("topic_phrase") or item.get("topic_key") or "").strip() or derive_topic_phrase(title)
    topic_uid = str(item.get("topic_uid") or "").strip() or build_topic_uid(topic_phrase, discovered_day, agent_id)

    platforms = _normalize_platforms(item.get("platforms") or item.get("platform"))
    source_note = str(item.get("source_note") or item.get("source") or item.get("来源说明") or "").strip()
    x_reference_url = str(item.get("x_reference_url") or item.get("url") or "").strip()
    core_points = str(item.get("core_points") or item.get("key_points") or item.get("description") or "").strip()
    content_angle = str(item.get("content_angle") or "").strip()
    raw_summary = str(item.get("raw_summary") or item.get("summary") or item.get("description") or "").strip()
    x_confirm_status = str(item.get("x_confirm_status") or item.get("source_status") or "").strip() or "X 专项确认缺失"
    emoji = str(item.get("emoji") or "").strip()

    return CandidateRecord(
        title=title,
        topic_phrase=topic_phrase,
        topic_uid=topic_uid,
        score=score,
        priority=str(item.get("priority") or _priority_from_score(score)).strip(),
        discovered_at_ms=discovered_at_ms,
        discovered_day=discovered_day,
        x_confirm_status=x_confirm_status,
        source_note=source_note,
        x_reference_url=x_reference_url,
        core_points=core_points,
        content_angle=content_angle,
        platforms=platforms,
        raw_summary=raw_summary,
        emoji=emoji,
    )


def build_bitable_fields(candidate: CandidateRecord, *, agent_id: str, task_name: str) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "选题标题": candidate.title,
        "topic_uid": candidate.topic_uid,
        "SCORE": candidate.score,
        "优先级": candidate.priority,
        "来源Agent": agent_id,
        "来源任务": task_name,
        "发现时间": candidate.discovered_at_ms,
        "X确认状态": candidate.x_confirm_status,
        "核心要点": candidate.core_points,
        "内容角度": candidate.content_angle,
        "适合平台": candidate.platforms,
        "发布状态": "未发布",
        "原始摘要": candidate.raw_summary,
    }
    if candidate.source_note:
        fields["来源说明"] = candidate.source_note
    if candidate.x_reference_url:
        fields["X参考链接"] = candidate.x_reference_url
    return fields


def build_delivery_payload(
    raw_payload: dict[str, Any],
    *,
    candidates: list[CandidateRecord],
    archive_target_path: str,
    write_status: str,
    created: list[str],
    updated: list[str],
    duplicate_matches: int,
) -> dict[str, Any]:
    scan_time_text = _scan_time_text(raw_payload)
    title = str(raw_payload.get("title") or "").strip() or f"AI 热点扫描 · {scan_time_text[:16].replace('T', ' ')}"
    items = [
        {
            "emoji": candidate.emoji or _emoji_from_score(candidate.score),
            "title": candidate.title,
            "score": candidate.score,
            "platforms": candidate.platforms,
            "description": _build_delivery_description(candidate),
        }
        for candidate in candidates
    ]
    payload = {
        "template": "ai-hotspot",
        "title": title,
        "summary": str(raw_payload.get("summary") or f"本轮已整理 {len(items)} 条候选项。").strip(),
        "count": len(items),
        "timestamp": str(raw_payload.get("timestamp") or scan_time_text).strip(),
        "next_check": str(raw_payload.get("next_check") or "").strip(),
        "archive_target_path": archive_target_path,
        "items": items,
        "thread_summary": {
            "notice": "AI 热点扫描已完成",
            "bullets": _build_summary_bullets(candidates, write_status=write_status, created=created, updated=updated, duplicate_matches=duplicate_matches),
            "footer": "详情见上一条完整卡片。",
        },
        "execution_meta": {
            "scan_time": scan_time_text,
            "bitable_write_status": write_status,
            "bitable_records_created": len(created),
            "bitable_records_updated": len(updated),
            "duplicate_matches": duplicate_matches,
            "data_source_managed_by": "feishu-bitable-only",
            "local_mirror_maintained": False,
        },
    }
    if created:
        payload["execution_meta"]["created_record_ids"] = created
    if updated:
        payload["execution_meta"]["updated_record_ids"] = updated
    if payload["next_check"] == "":
        payload.pop("next_check")
    return normalize_template_data("ai-hotspot", payload)


def run_cli(argv: list[str] | None = None, *, entry_script: Path | None = None) -> int:
    args = parse_args(argv)
    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()
    config_path = Path(args.bitable_config).resolve()
    project_root = Path(args.project_root).resolve() if args.project_root else (entry_script or Path(__file__).resolve()).parents[2]

    raw_payload = json.loads(input_path.read_text(encoding="utf-8"))
    config = json.loads(config_path.read_text(encoding="utf-8"))
    bitable = (config.get("bitable") or {})
    app_token = str(bitable.get("app_token") or "").strip()
    table_id = str(bitable.get("table_id") or "").strip()
    archive_target_path = str(bitable.get("url") or raw_payload.get("archive_target_path") or "").strip()
    if not app_token or not table_id:
        raise ValueError("bitable 配置缺少 app_token 或 table_id")

    scan_time_text = _scan_time_text(raw_payload)
    raw_items = raw_payload.get("items") or []
    candidates = [normalize_candidate(item, scan_time_text=scan_time_text, agent_id=args.agent_id, task_name=args.task_name) for item in raw_items]

    settings = build_settings(project_root=Path(project_root))
    access_token = resolve_access_token(settings, args.agent_id)

    created: list[str] = []
    updated: list[str] = []
    duplicate_matches = 0
    failures: list[str] = []

    for candidate in candidates:
        try:
            record_id, action, extra_duplicates = upsert_candidate(
                access_token=access_token,
                app_token=app_token,
                table_id=table_id,
                candidate=candidate,
                agent_id=args.agent_id,
                task_name=args.task_name,
            )
            duplicate_matches += extra_duplicates
            if action == "created":
                created.append(record_id)
            else:
                updated.append(record_id)
        except Exception as exc:  # pragma: no cover - exercised in integration
            failures.append(f"{candidate.title}: {exc}")

    if failures and (created or updated):
        write_status = "partial"
    elif failures:
        write_status = "failed"
    else:
        write_status = "success"

    payload = build_delivery_payload(
        raw_payload,
        candidates=candidates,
        archive_target_path=archive_target_path,
        write_status=write_status,
        created=created,
        updated=updated,
        duplicate_matches=duplicate_matches,
    )
    if failures:
        payload["execution_meta"]["bitable_write_errors"] = failures

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(str(output_path))
    return 0


def upsert_candidate(
    *,
    access_token: str,
    app_token: str,
    table_id: str,
    candidate: CandidateRecord,
    agent_id: str,
    task_name: str,
) -> tuple[str, str, int]:
    fields = build_bitable_fields(candidate, agent_id=agent_id, task_name=task_name)
    by_uid = search_records(
        access_token,
        app_token,
        table_id,
        filter_body={
            "conjunction": "and",
            "conditions": [{"field_name": "topic_uid", "operator": "is", "value": [candidate.topic_uid]}],
        },
    )
    selected, duplicate_matches = select_upsert_target(by_uid, candidate.discovered_day, candidate.topic_uid)
    if not selected:
        by_title = search_records(
            access_token,
            app_token,
            table_id,
            filter_body={
                "conjunction": "and",
                "conditions": [
                    {"field_name": "选题标题", "operator": "contains", "value": [candidate.topic_phrase]},
                    {"field_name": "来源任务", "operator": "is", "value": [task_name]},
                ],
            },
        )
        selected, duplicate_matches = select_upsert_target(by_title, candidate.discovered_day, candidate.topic_uid)

    if selected:
        record_id = str(selected["record_id"])
        update_record(access_token, app_token, table_id, record_id, fields)
        return record_id, "updated", duplicate_matches

    record_id = create_record(access_token, app_token, table_id, fields)
    return record_id, "created", duplicate_matches


def search_records(access_token: str, app_token: str, table_id: str, *, filter_body: dict[str, Any]) -> list[dict[str, Any]]:
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/search"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    payload = {"field_names": BITABLE_FIELD_NAMES, "automatic_fields": True, "filter": filter_body, "page_size": 50}
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    result = parse_response_json(response)
    if result.get("code") != 0:
        raise ValueError(f"bitable_search_failed: {result}")
    return ((result.get("data") or {}).get("items") or [])


def create_record(access_token: str, app_token: str, table_id: str, fields: dict[str, Any]) -> str:
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    response = requests.post(url, headers=headers, json={"fields": fields}, timeout=30)
    result = parse_response_json(response)
    if result.get("code") != 0:
        raise ValueError(f"bitable_create_failed: {result}")
    return str(((result.get("data") or {}).get("record") or {}).get("record_id") or "")


def update_record(access_token: str, app_token: str, table_id: str, record_id: str, fields: dict[str, Any]) -> None:
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    response = requests.put(url, headers=headers, json={"fields": fields}, timeout=30)
    result = parse_response_json(response)
    if result.get("code") != 0:
        raise ValueError(f"bitable_update_failed: {result}")


def _scan_time_text(raw_payload: dict[str, Any]) -> str:
    for key in ("scan_time", "timestamp"):
        value = str(raw_payload.get(key) or "").strip()
        if value:
            return value
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _build_delivery_description(candidate: CandidateRecord) -> str:
    parts = [candidate.core_points or candidate.raw_summary]
    if candidate.x_confirm_status:
        parts.append(f"X确认状态：{candidate.x_confirm_status}")
    return " | ".join(part for part in parts if part)


def _build_summary_bullets(
    candidates: list[CandidateRecord],
    *,
    write_status: str,
    created: list[str],
    updated: list[str],
    duplicate_matches: int,
) -> list[str]:
    bullets: list[str] = []
    if created:
        bullets.append(f"新增高分选题：{len(created)} 个")
    elif updated:
        bullets.append(f"更新既有选题：{len(updated)} 个")
    else:
        bullets.append("本轮未写入新选题")

    if candidates:
        top = sorted(candidates, key=lambda item: item.score, reverse=True)[0]
        bullets.append(f"最高优先级：{top.title}（SCORE {top.score}）")
        bullets.append(f"X确认状态：{_summarize_x_status(candidates)}")

    if write_status == "success":
        details: list[str] = []
        if created:
            details.append(f"新增 {len(created)} 条")
        if updated:
            details.append(f"更新 {len(updated)} 条")
        detail_text = "，".join(details) if details else "已确认写入"
        bullets.append(f"已写入飞书多维表格（{detail_text}）")
    elif write_status == "partial":
        bullets.append("Bitable 写入部分成功")
    else:
        bullets.append("Bitable 写入未确认成功")

    if duplicate_matches:
        bullets.append(f"命中历史重复记录：{duplicate_matches} 条（已收敛到同一 topic_uid）")
    return bullets


def _summarize_x_status(candidates: list[CandidateRecord]) -> str:
    statuses = [candidate.x_confirm_status for candidate in candidates if candidate.x_confirm_status]
    unique = list(dict.fromkeys(statuses))
    if not unique:
        return "未提供"
    if len(unique) == 1:
        return unique[0]
    return "；".join(unique)


def _normalize_platforms(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    if not text:
        return []
    for splitter in ("、", ",", "，", "/"):
        text = text.replace(splitter, "|")
    return [chunk.strip() for chunk in text.split("|") if chunk.strip()]


def _priority_from_score(score: int) -> str:
    if score >= 22:
        return "高优先级"
    if score >= 18:
        return "中优先级"
    return "待评估"


def _emoji_from_score(score: int) -> str:
    if score >= 25:
        return "🚨"
    if score >= 24:
        return "🔥"
    if score >= 22:
        return "⚡"
    return "•"


def _coerce_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value or "").strip()
    digits = "".join(ch for ch in text if ch.isdigit())
    if digits:
        return int(digits)
    raise ValueError(f"无法解析 SCORE: {value}")


def _parse_datetime_ms(value: Any) -> int:
    if isinstance(value, (int, float)):
        raw = int(value)
        return raw if raw > 10_000_000_000 else raw * 1000
    text = str(value or "").strip()
    if not text:
        raise ValueError("缺少发现时间")
    if text.isdigit():
        raw = int(text)
        return raw if raw > 10_000_000_000 else raw * 1000
    normalized = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        dt = datetime.strptime(text[:10], "%Y-%m-%d")
    return int(dt.timestamp() * 1000)


def _field_text(record: dict[str, Any], field_name: str) -> str:
    value = (record.get("fields") or {}).get(field_name)
    if isinstance(value, list):
        texts = []
        for item in value:
            if isinstance(item, dict):
                text = str(item.get("text") or "").strip()
                if text:
                    texts.append(text)
            elif str(item).strip():
                texts.append(str(item).strip())
        return " ".join(texts).strip()
    return str(value or "").strip()


def _field_day(record: dict[str, Any], field_name: str) -> str:
    value = (record.get("fields") or {}).get(field_name)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(int(value) / 1000).strftime("%Y-%m-%d")
    text = str(value or "").strip()
    if text.isdigit():
        raw = int(text)
        raw = raw if raw > 10_000_000_000 else raw * 1000
        return datetime.fromtimestamp(raw / 1000).strftime("%Y-%m-%d")
    if not text:
        return ""
    return text[:10]


def derive_topic_phrase(title: str) -> str:
    text = str(title or "").strip()
    ascii_tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9.+-]*", text)
    if ascii_tokens:
        tokens = [token.lower() for token in ascii_tokens]
        while tokens and tokens[0] in {
            "anthropic",
            "openai",
            "google",
            "deepmind",
            "xai",
            "meta",
            "nvidia",
            "mistral",
            "microsoft",
            "amazon",
            "xiaomi",
        }:
            tokens.pop(0)
        if tokens:
            return " ".join(tokens[:4])
    compact = re.sub(r"[：:，,。！!？?\s]+", "", text)
    return compact[:12] or text


def _slugify_topic_phrase(value: str) -> str:
    ascii_tokens = re.findall(r"[A-Za-z0-9]+", value.lower())
    if ascii_tokens:
        return "-".join(ascii_tokens[:6])
    compact = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", value)
    if compact:
        return compact[:12]
    return "topic"
