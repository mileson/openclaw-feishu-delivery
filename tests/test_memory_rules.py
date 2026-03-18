from __future__ import annotations

from pathlib import Path

from openclaw_feishu_cron_kit.memory_rules import (
    END_MARKER,
    START_MARKER,
    inject_delivery_memory_rules,
    list_configured_workspace_memory_paths,
    update_memory_file,
)


def test_inject_delivery_memory_rules_inserts_after_title(tmp_path: Path) -> None:
    project_root = tmp_path / "openclaw-feishu-delivery"
    project_root.mkdir()

    text = "# MEMORY.md - blogger\n\n## 工作记录\n\n- 初始化\n"
    updated, action = inject_delivery_memory_rules(text, project_root)

    assert action == "inserted"
    assert updated.startswith("# MEMORY.md - blogger\n\n" + START_MARKER)
    assert "`" + str(project_root / "scripts" / "send_message.py") + "`" in updated
    assert END_MARKER in updated


def test_inject_delivery_memory_rules_normalizes_legacy_section(tmp_path: Path) -> None:
    project_root = tmp_path / "openclaw-feishu-delivery"
    project_root.mkdir()

    text = """# MEMORY.md - product

## 飞书消息项目铁律（强制）

1. 所有结构化飞书消息统一使用：`/root/.openclaw/scripts/send_feishu_message.py`

## 工作记录

- 初始化
"""
    updated, action = inject_delivery_memory_rules(text, project_root)

    assert action == "normalized"
    assert "/root/.openclaw/scripts/send_feishu_message.py" not in updated
    assert START_MARKER in updated


def test_inject_delivery_memory_rules_strips_legacy_variants(tmp_path: Path) -> None:
    project_root = tmp_path / "openclaw-feishu-delivery"
    project_root.mkdir()

    text = """# MEMORY.md - coach

## 飞书消息铁律

所有飞书消息必须使用通用工具：

```bash
python3 /root/.openclaw/scripts/send_feishu_message.py --template "模板名称" --data 'JSON数据'
```

统一遵循：`/root/.openclaw/workspace/docs/feishu-message-standard.md`

## 当前状态

- 初始化
"""
    updated, action = inject_delivery_memory_rules(text, project_root)

    assert action == "normalized"
    assert "## 飞书消息铁律" not in updated
    assert "/root/.openclaw/scripts/send_feishu_message.py" not in updated
    assert "/root/.openclaw/workspace/docs/feishu-message-standard.md" not in updated
    assert "## 当前状态" in updated


def test_inject_delivery_memory_rules_strips_hr_legacy_variant(tmp_path: Path) -> None:
    project_root = tmp_path / "openclaw-feishu-delivery"
    project_root.mkdir()

    text = """# MEMORY.md - hr

## 飞书消息发送铁律（最高优先级）

### 唯一发送方式

```bash
python3 /root/.openclaw/scripts/send_feishu_message.py \\
  --template "模板名称" \\
  --data 'JSON数据'
```

## 任务执行铁律（强制）

- 初始化
"""
    updated, action = inject_delivery_memory_rules(text, project_root)

    assert action == "normalized"
    assert "## 飞书消息发送铁律（最高优先级）" not in updated
    assert "/root/.openclaw/scripts/send_feishu_message.py" not in updated
    assert "## 任务执行铁律（强制）" in updated


def test_inject_delivery_memory_rules_rewrites_observed_legacy_references(tmp_path: Path) -> None:
    project_root = tmp_path / "openclaw-feishu-delivery"
    project_root.mkdir()

    text = """# MEMORY.md - product

## 工作记录

- 通用工具`send_feishu_message.py`使用main账号的open_id导致跨应用错误
- 临时解决方案：使用message工具直接发送
- /root/.openclaw/workspace/docs/feishu-message-standard.md（新增skill-distribution模板）
"""
    updated, action = inject_delivery_memory_rules(text, project_root)

    assert action == "normalized"
    assert "send_feishu_message.py" not in updated
    assert "feishu-message-standard.md" not in updated
    assert "旧消息链路曾因账号接收者配置错误导致跨应用发送失败" in updated
    assert "当前统一使用项目内模板与账号配置发送" in updated
    assert str(project_root / "runtime" / "feishu-templates.local.json") in updated


def test_update_memory_file_supports_create_missing(tmp_path: Path) -> None:
    project_root = tmp_path / "openclaw-feishu-delivery"
    workspace_dir = tmp_path / "workspace-product"
    project_root.mkdir()

    result = update_memory_file(
        workspace_dir / "MEMORY.md",
        project_root,
        apply=True,
        create_missing=True,
    )

    assert result["changed"] is True
    memory_text = (workspace_dir / "MEMORY.md").read_text(encoding="utf-8")
    assert START_MARKER in memory_text
    assert "# MEMORY.md - workspace-product" in memory_text


def test_list_configured_workspace_memory_paths_reads_agent_workspaces(tmp_path: Path) -> None:
    config_path = tmp_path / "openclaw.json"
    config_path.write_text(
        """
        {
          "agents": {
            "list": [
              {"id": "main", "workspace": "/srv/openclaw/workspace"},
              {"id": "product", "workspace": "/srv/openclaw/workspace-product"},
              {"id": "coach", "workspace": "/srv/openclaw/workspace-coach"},
              {"id": "product", "workspace": "/srv/openclaw/workspace-product"}
            ]
          }
        }
        """.strip(),
        encoding="utf-8",
    )

    memory_paths = list_configured_workspace_memory_paths(config_path)

    assert memory_paths == [
        Path("/srv/openclaw/workspace/MEMORY.md"),
        Path("/srv/openclaw/workspace-product/MEMORY.md"),
        Path("/srv/openclaw/workspace-coach/MEMORY.md"),
    ]


def test_list_configured_workspace_memory_paths_supports_default_workspace_fallbacks(tmp_path: Path) -> None:
    config_path = tmp_path / "openclaw.json"
    config_path.write_text(
        """
        {
          "agents": {
            "list": [
              {"id": "main"},
              {"id": "security"}
            ]
          }
        }
        """.strip(),
        encoding="utf-8",
    )

    memory_paths = list_configured_workspace_memory_paths(config_path, state_dir=tmp_path)

    assert memory_paths == [
        tmp_path / "workspace" / "MEMORY.md",
        tmp_path / "workspace-security" / "MEMORY.md",
    ]
