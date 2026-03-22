"""Generic block helpers and scaffold utilities for Feishu card definitions.

Template-specific presentations live in feishu-templates.local.json (the single
source of truth).  This module only provides:

1. Generic block helper functions for scaffold scripts
2. Scaffold layout loader (reads from runtime/scaffold-layouts.json)
3. materialize_template_registry() for transport / metadata setup only
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


STANDARD_PANEL_STYLES: dict[str, dict[str, Any]] = {
    "default": {
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
    },
    "danger": {
        "title_color": "#CF1322",
    },
}


# ---------------------------------------------------------------------------
# Generic block helper functions (used by scaffold_agent_task.py)
# ---------------------------------------------------------------------------

def plain_text(template: str) -> dict[str, Any]:
    return {"type": "plain_text", "template": template}


def markdown(template: str) -> dict[str, Any]:
    return {"type": "markdown", "template": template}


def divider() -> dict[str, Any]:
    return {"type": "divider"}


def facts(title: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "facts", "title": title, "items": items}


def list_block(
    title: str,
    path: str,
    *,
    max_items: int | None = None,
    empty_text: str | None = None,
    show_title: bool | None = None,
) -> dict[str, Any]:
    block: dict[str, Any] = {
        "type": "list",
        "title": title,
        "path": path,
        "item_template": "{item}",
    }
    if max_items:
        block["max_items"] = max_items
    if empty_text:
        block["empty_text"] = empty_text
    if show_title is not None:
        block["show_title"] = show_title
    return block


def record_list(
    title: str,
    path: str,
    title_template: str,
    lines: list[str],
    *,
    max_items: int | None = None,
    empty_text: str | None = None,
    children_field: str | None = None,
    child_title_template: str | None = None,
    child_lines: list[str] | None = None,
    max_children: int | None = None,
    show_title: bool | None = None,
) -> dict[str, Any]:
    block: dict[str, Any] = {
        "type": "record_list",
        "title": title,
        "path": path,
        "title_template": title_template,
        "lines": lines,
    }
    if max_items:
        block["max_items"] = max_items
    if empty_text:
        block["empty_text"] = empty_text
    if children_field:
        block["children_field"] = children_field
    if child_title_template:
        block["child_title_template"] = child_title_template
    if child_lines:
        block["child_lines"] = child_lines
    if max_children:
        block["max_children"] = max_children
    if show_title is not None:
        block["show_title"] = show_title
    return block


def table_block(
    path: str,
    columns: list[dict[str, Any]],
    *,
    page_size: int | None = None,
    row_height: str | None = None,
    row_max_height: str | None = None,
    freeze_first_column: bool | None = None,
    header_style: dict[str, Any] | None = None,
    element_id: str | None = None,
    margin: str | None = None,
    empty_text: str | None = None,
) -> dict[str, Any]:
    block: dict[str, Any] = {
        "type": "table",
        "path": path,
        "columns": columns,
    }
    if page_size:
        block["page_size"] = page_size
    if row_height:
        block["row_height"] = row_height
    if row_max_height:
        block["row_max_height"] = row_max_height
    if freeze_first_column is not None:
        block["freeze_first_column"] = freeze_first_column
    if header_style:
        block["header_style"] = header_style
    if element_id:
        block["element_id"] = element_id
    if margin:
        block["margin"] = margin
    if empty_text:
        block["empty_text"] = empty_text
    return block


def note(template: str) -> dict[str, Any]:
    return {"type": "note", "template": template}


def collapsible_panel(
    title: str,
    blocks: list[dict[str, Any]],
    *,
    expanded: bool = False,
    style: str = "default",
    empty_text: str | None = None,
) -> dict[str, Any]:
    panel: dict[str, Any] = {
        "type": "collapsible_panel",
        "title": title,
        "expanded": expanded,
        "style": style,
        "blocks": blocks,
    }
    if empty_text:
        panel["empty_text"] = empty_text
    return panel


def collapsible_record_panels(
    path: str,
    panel_title_template: str,
    lines: list[str],
    *,
    max_items: int | None = None,
    children_field: str | None = None,
    child_title_template: str | None = None,
    child_lines: list[str] | None = None,
    max_children: int | None = None,
    expanded_first: bool = False,
    expanded_all: bool = False,
    style: str = "default",
    empty_text: str | None = None,
    blocks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    panel: dict[str, Any] = {
        "type": "collapsible_record_panels",
        "path": path,
        "panel_title_template": panel_title_template,
        "lines": lines,
        "expanded_first": expanded_first,
        "expanded_all": expanded_all,
        "style": style,
    }
    if max_items:
        panel["max_items"] = max_items
    if children_field:
        panel["children_field"] = children_field
    if child_title_template:
        panel["child_title_template"] = child_title_template
    if child_lines:
        panel["child_lines"] = child_lines
    if max_children:
        panel["max_children"] = max_children
    if empty_text:
        panel["empty_text"] = empty_text
    if blocks:
        panel["blocks"] = blocks
    return panel


# ---------------------------------------------------------------------------
# Layout presentation builders (used by scaffold)
# ---------------------------------------------------------------------------

def _layout_presentation(
    structure: str,
    blocks: list[dict[str, Any]],
    *,
    schema: str = "1.0",
    styles: dict[str, Any] | None = None,
) -> dict[str, Any]:
    presentation: dict[str, Any] = {
        "schema": schema,
        "structure": structure,
        "blocks": blocks,
    }
    if styles:
        presentation["styles"] = styles
    return presentation


def generic_presentation(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    return _layout_presentation("generic", blocks)


def collapsible_list_presentation(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    return _layout_presentation("collapsible-list", blocks, schema="2.0", styles={"panels": deepcopy(STANDARD_PANEL_STYLES)})


def grouped_panels_presentation(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    return _layout_presentation("grouped-panels", blocks, schema="2.0", styles={"panels": deepcopy(STANDARD_PANEL_STYLES)})


def panel_report_presentation(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    return _layout_presentation("panel-report", blocks, schema="2.0", styles={"panels": deepcopy(STANDARD_PANEL_STYLES)})


# ---------------------------------------------------------------------------
# Scaffold layout loader — reads from runtime/scaffold-layouts.json
# ---------------------------------------------------------------------------

_SCAFFOLD_LAYOUTS_CACHE: dict[str, dict[str, Any]] | None = None


def _resolve_scaffold_layouts_path() -> Path:
    return Path(__file__).resolve().parents[2] / "runtime" / "scaffold-layouts.json"


def load_scaffold_layouts(*, path: Path | None = None) -> dict[str, dict[str, Any]]:
    global _SCAFFOLD_LAYOUTS_CACHE
    if _SCAFFOLD_LAYOUTS_CACHE is not None and path is None:
        return _SCAFFOLD_LAYOUTS_CACHE
    target = path or _resolve_scaffold_layouts_path()
    if not target.exists():
        raise FileNotFoundError(f"Scaffold layouts file not found: {target}")
    layouts = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(layouts, dict):
        raise ValueError(f"scaffold-layouts.json must be a dict, got {type(layouts).__name__}")
    if path is None:
        _SCAFFOLD_LAYOUTS_CACHE = layouts
    return layouts


SCAFFOLD_LAYOUTS: dict[str, dict[str, Any]] = {}


def _ensure_scaffold_layouts() -> dict[str, dict[str, Any]]:
    global SCAFFOLD_LAYOUTS
    if not SCAFFOLD_LAYOUTS:
        try:
            SCAFFOLD_LAYOUTS = load_scaffold_layouts()
        except FileNotFoundError:
            pass
    return SCAFFOLD_LAYOUTS


def get_scaffold_layout(name: str) -> dict[str, Any]:
    layouts = _ensure_scaffold_layouts()
    layout = layouts.get(name)
    if not layout:
        raise ValueError(f"未知 layout: {name}")
    return deepcopy(layout)


# ---------------------------------------------------------------------------
# Template presentations — loaded from JSON config (single source of truth)
# ---------------------------------------------------------------------------

def load_template_presentations(templates_file: Path | str) -> dict[str, dict[str, Any]]:
    """Load presentation configs from the templates JSON file."""
    path = Path(templates_file)
    if not path.exists():
        raise FileNotFoundError(f"Templates file not found: {path}")
    registry = json.loads(path.read_text(encoding="utf-8"))
    templates = registry.get("templates", registry)
    return {
        name: deepcopy(cfg.get("presentation", {}))
        for name, cfg in templates.items()
        if isinstance(cfg, dict) and cfg.get("presentation")
    }


TEMPLATE_PRESENTATIONS: dict[str, dict[str, Any]] = {}


def _ensure_template_presentations() -> dict[str, dict[str, Any]]:
    """Lazy-load from the default templates file on first access."""
    global TEMPLATE_PRESENTATIONS
    if not TEMPLATE_PRESENTATIONS:
        try:
            default_path = Path(__file__).resolve().parents[2] / "runtime" / "feishu-templates.local.json"
            TEMPLATE_PRESENTATIONS = load_template_presentations(default_path)
        except FileNotFoundError:
            pass
    return TEMPLATE_PRESENTATIONS


def get_template_presentation(name: str) -> dict[str, Any]:
    presentations = _ensure_template_presentations()
    presentation = presentations.get(name)
    if not presentation:
        raise ValueError(f"未知模板 presentation: {name}")
    return deepcopy(presentation)


# ---------------------------------------------------------------------------
# materialize_template_registry — transport / metadata setup only
# ---------------------------------------------------------------------------

def materialize_template_registry(
    registry: dict[str, Any],
    *,
    overwrite_blocks: bool = False,
    drop_renderer: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Normalize transport and metadata in the template registry.

    Blocks are managed directly in JSON — this function only handles:
    - Setting default transport.provider to 'feishu'
    - Inferring transport.account from target_agents
    - Removing legacy 'renderer' field if drop_renderer=True
    """
    templates = registry.get("templates", registry)
    if not isinstance(templates, dict):
        raise ValueError("模板注册表必须包含 templates 对象")

    updated = deepcopy(registry)
    target_templates = updated.get("templates", updated)
    changes: list[dict[str, Any]] = []

    for template_name, template_config in list(target_templates.items()):
        if not isinstance(template_config, dict):
            continue

        route = deepcopy(template_config.get("route") or {})
        transport = deepcopy(route.get("transport") or {})
        change: dict[str, Any] = {"template": template_name}
        transport_changed = False

        if not transport.get("provider"):
            transport["provider"] = "feishu"
            transport_changed = True
        target_agents = template_config.get("target_agents") or []
        if not transport.get("account") and isinstance(target_agents, list) and len(target_agents) == 1 and target_agents[0]:
            transport["account"] = str(target_agents[0]).strip()
            transport_changed = True

        if transport_changed:
            route["transport"] = transport
            target_templates[template_name]["route"] = route
            change["transport"] = "updated"

        if drop_renderer and "renderer" in template_config:
            target_templates[template_name].pop("renderer", None)
            change["renderer"] = "removed"

        if change.keys() != {"template"}:
            changes.append(change)

    return updated, changes
