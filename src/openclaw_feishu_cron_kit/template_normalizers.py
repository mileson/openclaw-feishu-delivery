from __future__ import annotations

import re
from copy import deepcopy
from typing import Any


_SUCCESS_PHRASES = (
    "已写入飞书多维表格",
    "写入飞书多维表格",
    "Bitable 写入成功",
    "Bitable写入成功",
)


def normalize_template_data(template_name: str, data: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(data)
    if template_name == "ai-hotspot":
        return normalize_ai_hotspot_payload(normalized)
    return normalized


def normalize_ai_hotspot_payload(data: dict[str, Any]) -> dict[str, Any]:
    items = data.get("items") or []
    normalized_items = [_normalize_ai_hotspot_item(item) for item in items if isinstance(item, dict)]
    data["items"] = normalized_items
    data["count"] = len(normalized_items)

    if not str(data.get("summary") or "").strip():
        data["summary"] = f"本轮已整理 {len(normalized_items)} 条候选项。"

    bitable_success = is_bitable_write_success(data)
    data["archive_note"] = _build_archive_note(data.get("archive_target_path"), bitable_success)

    raw_summary = data.get("thread_summary")
    if isinstance(raw_summary, dict):
        data["thread_summary"] = {
            **raw_summary,
            "bullets": _sanitize_summary_bullets(
                raw_summary.get("bullets") or [],
                bitable_success=bitable_success,
                created_count=_coerce_int(_read_meta(data, "bitable_records_created")),
                updated_count=_coerce_int(_read_meta(data, "bitable_records_updated")),
            ),
        }

    return data


def is_bitable_write_success(data: dict[str, Any]) -> bool:
    status = _read_meta(data, "bitable_write_status")
    if isinstance(status, bool):
        return status
    if status is None:
        return False
    return str(status).strip().lower() == "success"


def _read_meta(data: dict[str, Any], key: str) -> Any:
    if key in data:
        return data.get(key)
    meta = data.get("execution_meta")
    if isinstance(meta, dict):
        return meta.get(key)
    return None


def _build_archive_note(target_path: Any, bitable_success: bool) -> str:
    target = str(target_path or "").strip()
    if not target:
        return ""
    if bitable_success:
        return f"归档目标表：{target}"
    return f"目标表（本轮未确认写入成功）：{target}"


def _normalize_ai_hotspot_item(item: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(item)
    normalized["score"] = _normalize_score(item.get("score"))
    normalized["platform"] = _normalize_platforms(item.get("platform"), item.get("platforms"))
    normalized["description"] = _normalize_description(item)
    normalized["emoji"] = _normalize_emoji(item.get("emoji"), normalized["score"])
    return normalized


def _normalize_score(value: Any) -> Any:
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value or "").strip()
    if not text:
        return ""
    match = re.search(r"(\d+)", text)
    if match:
        return int(match.group(1))
    return text


def _normalize_platforms(primary: Any, secondary: Any) -> str:
    if isinstance(primary, list):
        values = primary
    elif isinstance(secondary, list):
        values = secondary
    elif isinstance(primary, str):
        values = _split_platform_text(primary)
    elif isinstance(secondary, str):
        values = _split_platform_text(secondary)
    else:
        values = []

    cleaned = [str(item).strip() for item in values if str(item).strip()]
    return "、".join(dict.fromkeys(cleaned))


def _split_platform_text(value: str) -> list[str]:
    chunks = re.split(r"[、,/，\s]+", value.strip())
    return [chunk for chunk in chunks if chunk]


def _normalize_description(item: dict[str, Any]) -> str:
    description = str(item.get("description") or "").strip()
    if description:
        return description

    summary = str(item.get("summary") or "").strip()
    core_points = str(item.get("core_points") or item.get("key_points") or "").strip()
    x_status = str(item.get("x_confirm_status") or item.get("source_status") or "").strip()

    parts: list[str] = []
    if summary:
        parts.append(summary)
    elif core_points:
        parts.append(core_points)
    if x_status:
        parts.append(f"X确认状态：{x_status}")
    return " | ".join(parts)


def _normalize_emoji(value: Any, score: Any) -> str:
    emoji = str(value or "").strip()
    if emoji:
        return emoji
    numeric = _coerce_int(score)
    if numeric >= 25:
        return "🚨"
    if numeric >= 24:
        return "🔥"
    if numeric >= 22:
        return "⚡"
    return "•"


def _sanitize_summary_bullets(
    bullets: list[Any],
    *,
    bitable_success: bool,
    created_count: int,
    updated_count: int,
) -> list[str]:
    sanitized: list[str] = []
    had_bitable_claim = False
    for raw in bullets:
        bullet = str(raw or "").strip()
        if not bullet:
            continue
        if any(token in bullet for token in _SUCCESS_PHRASES):
            had_bitable_claim = True
            continue
        sanitized.append(bullet)

    if bitable_success:
        if created_count or updated_count:
            details: list[str] = []
            if created_count:
                details.append(f"新增 {created_count} 条")
            if updated_count:
                details.append(f"更新 {updated_count} 条")
            sanitized.append(f"已写入飞书多维表格（{'，'.join(details)}）")
        elif had_bitable_claim:
            sanitized.append("已写入飞书多维表格")
    elif had_bitable_claim:
        sanitized.append("Bitable 写入未确认成功")

    return sanitized


def _coerce_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value or "").strip()
    if not text:
        return 0
    match = re.search(r"-?\d+", text)
    if not match:
        return 0
    return int(match.group(0))
