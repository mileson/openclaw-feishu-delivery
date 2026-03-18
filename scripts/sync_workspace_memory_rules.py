#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from openclaw_feishu_cron_kit.memory_rules import (
    infer_openclaw_config_path,
    infer_openclaw_state_dir,
    list_configured_workspace_memory_paths,
    update_memory_file,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync managed OpenClaw delivery rules into workspace MEMORY.md files")
    parser.add_argument("--project-root", default=str(ROOT))
    parser.add_argument("--openclaw-state-dir")
    parser.add_argument("--openclaw-config")
    parser.add_argument("--workspace-dir", action="append", default=[], help="只处理指定 workspace 目录，可重复")
    parser.add_argument("--create-missing", action="store_true")
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project_root = Path(args.project_root).expanduser().resolve()
    state_dir = infer_openclaw_state_dir(
        project_root,
        Path(args.openclaw_state_dir).expanduser() if args.openclaw_state_dir else None,
    )
    config_path = infer_openclaw_config_path(
        project_root,
        Path(args.openclaw_config).expanduser() if args.openclaw_config else None,
        Path(args.openclaw_state_dir).expanduser() if args.openclaw_state_dir else None,
    )
    if not config_path.exists():
        raise SystemExit(f"OpenClaw config not found: {config_path}")

    if args.workspace_dir:
        memory_paths = [Path(raw).expanduser().resolve() / "MEMORY.md" for raw in args.workspace_dir]
    else:
        memory_paths = list_configured_workspace_memory_paths(config_path, state_dir=state_dir)

    results = [
        update_memory_file(
            memory_path,
            project_root,
            apply=args.apply,
            create_missing=args.create_missing,
        )
        for memory_path in memory_paths
    ]

    summary = {
        "mode": "apply" if args.apply else "dry-run",
        "projectRoot": str(project_root),
        "stateDir": str(state_dir),
        "configPath": str(config_path),
        "workspaceCount": len(memory_paths),
        "changedCount": sum(1 for item in results if item["changed"]),
        "results": results,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
