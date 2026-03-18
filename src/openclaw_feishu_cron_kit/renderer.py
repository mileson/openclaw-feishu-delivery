from __future__ import annotations

import json
import re
from typing import Any


_PLACEHOLDER_RE = re.compile(r"\{([^{}]+)\}")
_MISSING = object()
_PANEL_DEFAULT_STYLE = {
    "title_color": "#333333",
    "header_background_color": "grey",
    "header_vertical_align": "center",
    "icon_token": "down-small-ccm_outlined",
    "icon_color": "#9AA0A6",
    "icon_size": "16px 16px",
    "icon_position": "right",
    "icon_expanded_angle": -180,
    "border_color": "grey",
    "corner_radius": "5px",
    "padding": "8px 8px 8px 8px",
}


def _markdown_element(content: str) -> dict[str, Any]:
    return {
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": content,
        },
    }


def _note_element(content: str) -> dict[str, Any]:
    return {
        "tag": "note",
        "elements": [
            {
                "tag": "plain_text",
                "content": content,
            }
        ],
    }


def _plain_text_element(content: str) -> dict[str, Any]:
    return {
        "tag": "div",
        "text": {
            "tag": "plain_text",
            "content": content,
        },
    }


def _panel_markdown_element(content: str) -> dict[str, Any]:
    return {"tag": "markdown", "content": content}


def _derive_context(value: Any) -> dict[str, Any]:
    context: dict[str, Any] = {}
    if isinstance(value, dict):
        context.update(value)
        for key, item in value.items():
            if isinstance(item, list):
                context[f"{key}_count"] = len(item)
    elif isinstance(value, list):
        context["item_count"] = len(value)
    else:
        context["item"] = value
    return context


def _resolve_path(payload: Any, path: str) -> Any:
    current = payload
    for chunk in path.split("."):
        key = chunk.strip()
        if not key:
            return _MISSING
        if isinstance(current, dict):
            if key not in current:
                return _MISSING
            current = current[key]
            continue
        return _MISSING
    return current


def _stringify(value: Any) -> str:
    if value is _MISSING or value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        if not value:
            return ""
        if all(not isinstance(item, (dict, list)) for item in value):
            return "、".join(str(item).strip() for item in value if str(item).strip())
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value).strip()


def _render_template(template: str, root: dict[str, Any], item: Any | None = None) -> str:
    if not template:
        return ""

    context: dict[str, Any] = {}
    context.update(_derive_context(root))
    if isinstance(root, dict):
        context.update(root)
    if item is not None:
        context.update(_derive_context(item))
        if isinstance(item, dict):
            context.update(item)
        else:
            context["item"] = item

    def replace(match: re.Match[str]) -> str:
        token = match.group(1).strip()
        if not token:
            return ""
        value = _resolve_path(context, token)
        if value is _MISSING and isinstance(root, dict):
            value = _resolve_path(root, token)
        return _stringify(value)

    return _PLACEHOLDER_RE.sub(replace, template).strip()


def _normalize_schema(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"2", "2.0", "schema_2_0", "schema2", "lark.card/v2", "feishu.card/v2"}:
        return "2.0"
    return "1.0"


def _get_presentation_header(presentation: dict[str, Any]) -> dict[str, Any]:
    header = presentation.get("header")
    return header if isinstance(header, dict) else {}


def _get_header_template(template_config: dict[str, Any], presentation: dict[str, Any]) -> str:
    header = _get_presentation_header(presentation)
    return str(header.get("template") or template_config.get("header_template") or "blue").strip() or "blue"


def _get_header_title_template(presentation: dict[str, Any]) -> str:
    header = _get_presentation_header(presentation)
    return str(header.get("title_template") or presentation.get("header_title_template") or "").strip()


def _get_card_config(presentation: dict[str, Any]) -> dict[str, Any]:
    config = presentation.get("config")
    return config if isinstance(config, dict) else {}


def _get_styles(presentation: dict[str, Any]) -> dict[str, Any]:
    styles = presentation.get("styles")
    return styles if isinstance(styles, dict) else {}


def _merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def _resolve_panel_style(block: dict[str, Any], presentation: dict[str, Any]) -> dict[str, Any]:
    styles = _get_styles(presentation)
    panel_styles = styles.get("panels")
    panel_presets = panel_styles if isinstance(panel_styles, dict) else {}

    merged = dict(_PANEL_DEFAULT_STYLE)
    default_preset = panel_presets.get("default")
    if isinstance(default_preset, dict):
        merged = _merge_dict(merged, default_preset)

    style_ref = block.get("style") or block.get("panel_style") or "default"
    if isinstance(style_ref, str):
        named_style = panel_presets.get(style_ref)
        if isinstance(named_style, dict):
            merged = _merge_dict(merged, named_style)
    elif isinstance(style_ref, dict):
        merged = _merge_dict(merged, style_ref)

    overrides = block.get("style_overrides")
    if isinstance(overrides, dict):
        merged = _merge_dict(merged, overrides)
    return merged


def _render_fact_lines(items: list[dict[str, Any]], root: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for item in items:
        label = str(item.get("label") or "").strip()
        value_template = str(item.get("template") or "").strip()
        path = str(item.get("path") or "").strip()
        if value_template:
            value_text = _render_template(value_template, root)
        elif path:
            value_text = _stringify(_resolve_path(root, path))
        else:
            value_text = ""
        if not value_text:
            continue
        if label:
            lines.append(f"- **{label}**：{value_text}")
        else:
            lines.append(f"- {value_text}")
    return lines


def _render_collection_lines(block: dict[str, Any], root: dict[str, Any]) -> tuple[str, list[str]]:
    path = str(block.get("path") or block.get("field") or "").strip()
    values = _resolve_path(root, path) if path else _MISSING
    if not isinstance(values, list):
        values = []

    empty_text = _render_template(str(block.get("empty_text") or "").strip(), root)
    if not values and not empty_text:
        return "", []

    title = _render_template(str(block.get("title") or block.get("title_template") or "").strip(), root)
    max_items = int(block.get("max_items") or 0) or len(values)
    lines: list[str] = []

    if not values and empty_text:
        lines.append(empty_text)
        return title, lines

    for index, item in enumerate(values[:max_items], start=1):
        record_lines = _render_record_lines(block, root, item, index)
        rendered = "\n".join(line for line in record_lines if line).strip()
        if rendered:
            lines.append(rendered)
    return title, lines


def _render_record_lines(
    block: dict[str, Any],
    root: dict[str, Any],
    item: Any,
    index: int,
    *,
    include_title: bool = True,
) -> list[str]:
    lines: list[str] = []
    title_template = str(block.get("title_template") or block.get("item_template") or "{item}").strip()
    title = _render_template(title_template, root, item)
    if not title:
        fallback = _stringify(item)
        title = f"{index}. {fallback}" if block.get("ordered") else fallback
    elif block.get("ordered"):
        title = f"{index}. {title}"
    if include_title and title:
        lines.append(title)

    for template in block.get("lines") or []:
        rendered = _render_template(str(template), root, item)
        if rendered:
            lines.append(rendered)

    child_field = str(block.get("children_field") or "").strip()
    if child_field:
        children = []
        if isinstance(item, dict):
            raw_children = _resolve_path(item, child_field)
            if isinstance(raw_children, list):
                children = raw_children
        max_children = int(block.get("max_children") or 0) or len(children)
        for child in children[:max_children]:
            child_title_template = str(block.get("child_title_template") or block.get("child_item_template") or "{item}").strip()
            child_title = _render_template(child_title_template, root, child)
            child_lines = [f"  - {child_title or _stringify(child)}"]
            for template in block.get("child_lines") or []:
                rendered = _render_template(str(template), root, child)
                if rendered:
                    child_lines.append(f"    {rendered}")
            lines.extend(child_lines)
    return lines


def _render_lines_as_elements(
    title: str,
    lines: list[str],
    *,
    surface: str,
    show_title_default: bool = True,
    show_title: bool | None = None,
) -> list[dict[str, Any]]:
    elements: list[dict[str, Any]] = []
    should_show_title = show_title if show_title is not None else show_title_default
    if title and should_show_title:
        title_text = f"**{title}**"
        elements.append(_panel_markdown_element(title_text) if surface == "panel" else _markdown_element(title_text))
    for line in lines:
        if not line:
            continue
        elements.append(_panel_markdown_element(line) if surface == "panel" else _markdown_element(line))
    return elements


def _render_collection_block(block: dict[str, Any], root: dict[str, Any], *, surface: str) -> list[dict[str, Any]]:
    title, lines = _render_collection_lines(block, root)
    if not lines:
        return []
    explicit_show_title = block.get("show_title")
    return _render_lines_as_elements(
        title,
        lines,
        surface=surface,
        show_title_default=(surface != "panel"),
        show_title=explicit_show_title if isinstance(explicit_show_title, bool) else None,
    )


def _render_facts_block(block: dict[str, Any], root: dict[str, Any], *, surface: str) -> list[dict[str, Any]]:
    lines = _render_fact_lines(block.get("items") or [], root)
    if not lines:
        return []
    title = _render_template(str(block.get("title") or ""), root)
    content_lines = []
    if title:
        content_lines.append(f"**{title}**")
    content_lines.extend(lines)
    content = "\n".join(content_lines)
    return [_panel_markdown_element(content)] if surface == "panel" else [_markdown_element(content)]


def _render_text_block(block: dict[str, Any], root: dict[str, Any], *, surface: str, markdown: bool) -> list[dict[str, Any]]:
    content = _render_template(str(block.get("template") or ""), root)
    if not content:
        return []
    if surface == "panel":
        return [_panel_markdown_element(content)]
    if markdown:
        return [_markdown_element(content)]
    return [_plain_text_element(content)]


def _render_nested_blocks(
    blocks: list[dict[str, Any]],
    root: dict[str, Any],
    presentation: dict[str, Any],
    *,
    surface: str,
) -> list[dict[str, Any]]:
    elements: list[dict[str, Any]] = []
    for raw_block in blocks:
        if not isinstance(raw_block, dict):
            continue
        block_elements = _render_block(raw_block, root, presentation, surface=surface)
        if not block_elements:
            continue
        if elements and elements[-1] == {"tag": "hr"} and block_elements[0] == {"tag": "hr"}:
            continue
        elements.extend(block_elements)

    while elements and elements[-1] == {"tag": "hr"}:
        elements.pop()
    return elements


def _render_collapsible_panel(block: dict[str, Any], root: dict[str, Any], presentation: dict[str, Any]) -> list[dict[str, Any]]:
    title = _render_template(str(block.get("title") or block.get("title_template") or "").strip(), root)
    child_blocks = block.get("blocks") or block.get("elements") or []
    nested = child_blocks if isinstance(child_blocks, list) else []
    elements = _render_nested_blocks(nested, root, presentation, surface="panel")

    if not elements:
        empty_text = _render_template(str(block.get("empty_text") or "暂无内容"), root)
        if empty_text:
            elements = [_panel_markdown_element(empty_text)]

    if not elements:
        return []

    style = _resolve_panel_style(block, presentation)
    return [
        {
            "tag": "collapsible_panel",
            "expanded": bool(block.get("expanded", False)),
            "header": {
                "title": {
                    "tag": "markdown",
                    "content": f"**<font color='{style['title_color']}'>{title}</font>**",
                },
                "background_color": style["header_background_color"],
                "vertical_align": style["header_vertical_align"],
                "icon": {
                    "tag": "standard_icon",
                    "token": style["icon_token"],
                    "color": style["icon_color"],
                    "size": style["icon_size"],
                },
                "icon_position": style["icon_position"],
                "icon_expanded_angle": style["icon_expanded_angle"],
            },
            "border": {
                "color": style["border_color"],
                "corner_radius": style["corner_radius"],
            },
            "padding": style["padding"],
            "elements": elements,
        }
    ]


def _render_collapsible_record_panels(block: dict[str, Any], root: dict[str, Any], presentation: dict[str, Any]) -> list[dict[str, Any]]:
    path = str(block.get("path") or block.get("field") or "").strip()
    values = _resolve_path(root, path) if path else _MISSING
    if not isinstance(values, list) or not values:
        return []

    max_items = int(block.get("max_items") or 0) or len(values)
    title_template = str(block.get("panel_title_template") or block.get("title_template") or block.get("title") or "").strip()
    expanded_first = bool(block.get("expanded_first", False))
    expanded_all = bool(block.get("expanded_all", False))
    style = block.get("style") or "default"
    style_overrides = block.get("style_overrides")

    panels: list[dict[str, Any]] = []
    for index, item in enumerate(values[:max_items], start=1):
        panel_title = _render_template(title_template, root, item)
        if not panel_title:
            panel_title = _stringify(item) or f"记录 {index}"

        line_block = dict(block)
        line_block["title_template"] = str(block.get("item_template") or block.get("record_title_template") or "").strip()
        panel_lines = _render_record_lines(line_block, root, item, index, include_title=False)
        nested_blocks = block.get("blocks") or []
        panel_blocks: list[dict[str, Any]] = [{"type": "markdown", "template": line} for line in panel_lines]
        if isinstance(nested_blocks, list):
            panel_blocks.extend(nested_blocks)

        merged_root = root
        if isinstance(item, dict):
            merged_root = dict(root)
            merged_root.update(item)

        panel_block: dict[str, Any] = {
            "type": "collapsible_panel",
            "title": panel_title,
            "expanded": expanded_all or (expanded_first and index == 1) or bool(block.get("expanded", False)),
            "style": style,
            "blocks": panel_blocks,
            "empty_text": block.get("empty_text") or "暂无内容",
        }
        if isinstance(style_overrides, dict):
            panel_block["style_overrides"] = style_overrides

        rendered = _render_collapsible_panel(panel_block, merged_root, presentation)
        if rendered:
            panels.extend(rendered)
    return panels


def _render_block(
    block: dict[str, Any],
    root: dict[str, Any],
    presentation: dict[str, Any],
    *,
    surface: str,
) -> list[dict[str, Any]]:
    block_type = str(block.get("type") or "").strip()
    if block_type == "divider":
        return [{"tag": "hr"}]
    if block_type in {"text", "plain_text"}:
        return _render_text_block(block, root, surface=surface, markdown=False)
    if block_type == "markdown":
        return _render_text_block(block, root, surface=surface, markdown=True)
    if block_type == "facts":
        return _render_facts_block(block, root, surface=surface)
    if block_type in {"list", "record_list"}:
        return _render_collection_block(block, root, surface=surface)
    if block_type == "collapsible_panel":
        if surface == "panel":
            return []
        return _render_collapsible_panel(block, root, presentation)
    if block_type == "collapsible_record_panels":
        if surface == "panel":
            return []
        return _render_collapsible_record_panels(block, root, presentation)
    if block_type == "note":
        content = _render_template(str(block.get("template") or ""), root)
        return [_note_element(content)] if content else []
    return []


def _build_blocks_card(template_name: str, template_config: dict[str, Any], data: dict[str, Any]) -> dict[str, Any] | None:
    presentation = template_config.get("presentation") or {}
    blocks = presentation.get("blocks") or []
    if not isinstance(blocks, list) or not blocks:
        return None

    title_template = _get_header_title_template(presentation)
    title = (
        _render_template(title_template, data)
        if title_template
        else str(data.get("title") or template_config.get("description") or template_name)
    )
    schema = _normalize_schema(presentation.get("schema"))
    elements = _render_nested_blocks(blocks, data, presentation, surface="body")
    if not elements:
        return None

    header = {
        "template": _get_header_template(template_config, presentation),
        "title": {"tag": "plain_text", "content": title},
    }
    if schema == "2.0":
        return {
            "schema": "2.0",
            "header": header,
            "body": {"elements": elements},
        }

    card_config = {"wide_screen_mode": True}
    card_config.update(_get_card_config(presentation))
    return {"config": card_config, "header": header, "elements": elements}


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
    configured_card = _build_blocks_card(template_name, template_config, data)
    if configured_card:
        return configured_card

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
        elements.append(_note_element(f"归档文件：{archive_target_path}"))

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
        "post": {
            "zh_cn": {
                "title": f"{thread_title} · 最新摘要",
                "content": content,
            }
        }
    }


def build_summary_text(summary_data: dict[str, Any]) -> dict[str, Any]:
    notice = summary_data["notice"]
    bullets = summary_data["bullets"]
    footer = summary_data.get("footer")
    mention_open_ids = summary_data.get("mention_open_ids") or []

    lines: list[str] = []
    if mention_open_ids:
        lines.append(" ".join(f'<at user_id="{open_id}"></at>' for open_id in mention_open_ids))
    lines.append(notice)
    lines.append("【摘要】")
    lines.extend([f"- {bullet}" for bullet in bullets])
    if footer:
        lines.append(footer)
    return {"text": "\n".join(lines)}
