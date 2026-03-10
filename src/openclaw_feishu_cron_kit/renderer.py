from __future__ import annotations

from typing import Any


def _as_markdown_item(item: dict[str, Any]) -> str:
    parts: list[str] = []
    emoji = item.get("emoji") or "•"
    title = item.get("title") or "未命名项目"
    score = item.get("score")
    platform = item.get("platform")
    description = item.get("description") or ""
    first_line = f"{emoji} **{title}**"
    if score:
        first_line += f"（{score}）"
    parts.append(first_line)
    if description:
        parts.append(f"> {description}")
    if platform:
        parts.append(f"`平台`：{platform}")
    return "\n".join(parts)


def build_generic_card(template_name: str, template_config: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    presentation = template_config.get("presentation") or {}
    title = data.get("title") or presentation.get("header_title_template") or template_config.get("description") or template_name
    summary = data.get("summary") or f"已生成 1 条 `{template_name}` 报告。"
    timestamp = data.get("timestamp")
    archive_target_path = data.get("archive_target_path")
    items = data.get("items") or []
    sections = data.get("sections") or []

    elements: list[dict[str, Any]] = [
        {
            "tag": "div",
            "text": {"tag": "lark_md", "content": f"✅ **{title}**\n{summary}"},
        }
    ]

    if timestamp:
        elements.append(
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"📅 {timestamp}"},
            }
        )

    if items:
        elements.append({"tag": "hr"})
        for item in items:
            elements.append(
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": _as_markdown_item(item)},
                }
            )

    for section in sections:
        section_title = section.get("title") or "补充信息"
        lines = section.get("lines") or []
        if not lines:
            continue
        elements.append({"tag": "hr"})
        block = [f"**{section_title}**"]
        block.extend([f"- {line}" for line in lines])
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(block)}})

    if archive_target_path:
        elements.append({"tag": "hr"})
        elements.append(
            {
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": f"归档文件：{archive_target_path}",
                    }
                ],
            }
        )

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": template_config.get("header_template", "blue"),
            "title": {"tag": "plain_text", "content": title},
        },
        "elements": elements,
    }


def build_summary_post(thread_title: str, summary_data: dict[str, Any]) -> dict[str, Any]:
    notice = summary_data["notice"]
    bullets = summary_data["bullets"]
    footer = summary_data.get("footer")
    mention_open_ids = summary_data.get("mention_open_ids") or []

    first_line: list[dict[str, Any]] = []
    for open_id in mention_open_ids:
        first_line.append({"tag": "at", "user_id": open_id})
        first_line.append({"tag": "text", "text": " "})
    first_line.append({"tag": "text", "text": notice})

    content = [
        first_line,
        [{"tag": "text", "text": "【摘要】"}],
    ]
    for bullet in bullets:
        content.append([{"tag": "text", "text": f"- {bullet}"}])
    if footer:
        content.append([{"tag": "text", "text": footer}])

    return {
        "title": f"{thread_title} · 最新摘要",
        "content": content,
    }
