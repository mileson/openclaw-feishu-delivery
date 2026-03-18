from __future__ import annotations

import json
import os
import re
from pathlib import Path


START_MARKER = "<!-- openclaw-feishu-delivery:start -->"
END_MARKER = "<!-- openclaw-feishu-delivery:end -->"
LEGACY_SECTION_TITLE = "## 飞书消息项目铁律（强制）"
LEGACY_SECTION_TITLES = [
    LEGACY_SECTION_TITLE,
    "## 🔔 飞书消息发送铁律（最高优先级）",
    "## 飞书消息发送铁律（最高优先级）",
    "## 飞书消息铁律",
    "## 飞书消息铁律（强制）",
]
MANAGED_BLOCK_TOKEN = "__OPENCLAW_DELIVERY_MANAGED_BLOCK__"

MANAGED_BLOCK_RE = re.compile(
    rf"{re.escape(START_MARKER)}\n.*?\n{re.escape(END_MARKER)}",
    flags=re.S,
)
LEGACY_SECTION_RE = re.compile(
    rf"(?ms)^(?:{'|'.join(re.escape(title) for title in LEGACY_SECTION_TITLES)})\n.*?(?=^## |\Z)"
)
LEGACY_LINE_REPLACEMENTS = (
    (
        re.compile(
            r"^- 通用工具`send_feishu_message\.py`使用main账号的open_id导致跨应用错误$",
            flags=re.M,
        ),
        "- 旧消息链路曾因账号接收者配置错误导致跨应用发送失败",
    ),
    (
        re.compile(r"^- 临时解决方案：使用message工具直接发送$", flags=re.M),
        "- 当前统一使用项目内模板与账号配置发送",
    ),
)


def build_delivery_memory_rules_section(project_root: Path) -> str:
    root = project_root.expanduser().resolve()
    runtime_dir = root / "runtime"
    docs_dir = root / "docs"
    lines = [
        LEGACY_SECTION_TITLE,
        "",
        f"1. 所有结构化飞书消息统一使用：`{root / 'scripts' / 'send_message.py'}`",
        "2. 路由由模板配置决定，禁止手填 `--target-id / --target-type / --delivery-channel / --thread-*`",
        "3. 禁止硬编码消息 JSON 结构，模板样式与 route 都交给 runtime 配置",
        "4. runtime 配置入口：",
        f"   - `{runtime_dir / 'feishu-templates.local.json'}`",
        f"   - `{runtime_dir / 'accounts.local.json'}`",
        "5. 文档入口：",
        f"   - `{root / 'README.md'}`",
        f"   - `{docs_dir / 'openclaw-runtime-workflow.md'}`",
        f"   - `{docs_dir / 'template-contract.md'}`",
        f"   - `{docs_dir / 'agent-onboarding.md'}`",
        f"6. 新增模板或首个任务时，优先使用：`{root / 'scripts' / 'scaffold_agent_task.py'}`",
        "7. 发送失败必须记录重试过程",
    ]
    return "\n".join(lines).rstrip()


def build_managed_delivery_memory_block(project_root: Path) -> str:
    return "\n".join(
        [
            START_MARKER,
            build_delivery_memory_rules_section(project_root),
            END_MARKER,
        ]
    )


def infer_openclaw_state_dir(project_root: Path, explicit_state_dir: Path | None = None) -> Path:
    if explicit_state_dir is not None:
        return explicit_state_dir.expanduser().resolve()

    root = project_root.expanduser().resolve()
    if root.parent.name == "projects":
        return root.parent.parent.resolve()

    config_path = os.getenv("OPENCLAW_CONFIG_PATH")
    if config_path:
        return Path(config_path).expanduser().resolve().parent

    for env_name in ("OPENCLAW_STATE_DIR", "OPENCLAW_HOME"):
        value = os.getenv(env_name)
        if value:
            return Path(value).expanduser().resolve()

    return Path("~/.openclaw").expanduser().resolve()


def infer_openclaw_config_path(
    project_root: Path,
    explicit_config_path: Path | None = None,
    explicit_state_dir: Path | None = None,
) -> Path:
    if explicit_config_path is not None:
        return explicit_config_path.expanduser().resolve()

    config_path = os.getenv("OPENCLAW_CONFIG_PATH")
    if config_path:
        return Path(config_path).expanduser().resolve()

    state_dir = infer_openclaw_state_dir(project_root, explicit_state_dir)
    return state_dir / "openclaw.json"


def insert_managed_block(text: str, block: str) -> str:
    stripped = text.strip()
    if not stripped:
        return block

    lines = text.splitlines()
    if lines and lines[0].startswith("# "):
        insert_at = 1
        while insert_at < len(lines) and not lines[insert_at].strip():
            insert_at += 1
        prefix = "\n".join(lines[:insert_at]).rstrip()
        suffix = "\n".join(lines[insert_at:]).lstrip("\n")
        if suffix:
            return f"{prefix}\n\n{block}\n\n{suffix}"
        return f"{prefix}\n\n{block}"

    return f"{block}\n\n{text.lstrip()}"


def cleanup_blank_lines(text: str) -> str:
    compact = re.sub(r"\n{3,}", "\n\n", text)
    return compact.strip()


def strip_legacy_sections(text: str) -> str:
    return cleanup_blank_lines(LEGACY_SECTION_RE.sub("", text))


def normalize_legacy_reference_lines(text: str, project_root: Path) -> str:
    updated = text
    for pattern, replacement in LEGACY_LINE_REPLACEMENTS:
        updated = pattern.sub(replacement, updated)

    legacy_standard = "/root/.openclaw/workspace/docs/feishu-message-standard.md（新增skill-distribution模板）"
    if legacy_standard in updated:
        runtime_file = project_root.expanduser().resolve() / "runtime" / "feishu-templates.local.json"
        updated = updated.replace(
            legacy_standard,
            f"{runtime_file}（skill-distribution 模板配置）",
        )
    return cleanup_blank_lines(updated)


def inject_delivery_memory_rules(memory_text: str, project_root: Path) -> tuple[str, str]:
    normalized = memory_text.rstrip("\n")
    block = build_managed_delivery_memory_block(project_root)

    if MANAGED_BLOCK_RE.search(normalized):
        staged = MANAGED_BLOCK_RE.sub(MANAGED_BLOCK_TOKEN, normalized, count=1)
        cleaned = normalize_legacy_reference_lines(strip_legacy_sections(staged), project_root)
        updated = cleaned.replace(MANAGED_BLOCK_TOKEN, block, 1)
        return updated.rstrip() + "\n", "replaced"

    cleaned = normalize_legacy_reference_lines(strip_legacy_sections(normalized), project_root)
    if cleaned != normalized:
        updated = insert_managed_block(cleaned, block)
        return updated.rstrip() + "\n", "normalized"

    updated = insert_managed_block(normalized, block)
    return updated.rstrip() + "\n", "inserted"


def update_memory_file(
    memory_path: Path,
    project_root: Path,
    *,
    apply: bool = False,
    create_missing: bool = False,
) -> dict[str, object]:
    if not memory_path.exists() and not create_missing:
        return {
            "memoryPath": str(memory_path),
            "exists": False,
            "changed": False,
            "action": "missing",
        }

    if memory_path.exists():
        original = memory_path.read_text(encoding="utf-8")
    else:
        workspace_name = memory_path.parent.name
        original = f"# MEMORY.md - {workspace_name}\n"

    updated, action = inject_delivery_memory_rules(original, project_root)
    changed = updated != original

    if changed and apply:
        memory_path.parent.mkdir(parents=True, exist_ok=True)
        memory_path.write_text(updated, encoding="utf-8")

    return {
        "memoryPath": str(memory_path),
        "exists": memory_path.exists(),
        "changed": changed,
        "action": action if changed else "unchanged",
    }


def list_configured_workspace_memory_paths(
    openclaw_config_path: Path,
    *,
    state_dir: Path | None = None,
) -> list[Path]:
    config_path = openclaw_config_path.expanduser().resolve()
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    base_dir = (state_dir or config_path.parent).expanduser().resolve()

    memory_paths: list[Path] = []
    seen: set[str] = set()

    for agent in payload.get("agents", {}).get("list", []):
        agent_id = (agent.get("id") or "").strip()
        if not agent_id:
            continue

        raw_workspace = (agent.get("workspace") or "").strip()
        if raw_workspace:
            workspace_dir = Path(raw_workspace).expanduser()
            if not workspace_dir.is_absolute():
                workspace_dir = base_dir / workspace_dir
        elif agent_id == "main":
            workspace_dir = base_dir / "workspace"
        else:
            workspace_dir = base_dir / f"workspace-{agent_id}"

        workspace_key = str(workspace_dir.resolve())
        if workspace_key in seen:
            continue
        seen.add(workspace_key)
        memory_paths.append(Path(workspace_key) / "MEMORY.md")

    return memory_paths
