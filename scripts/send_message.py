#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from openclaw_feishu_cron_kit.core import run_cli


if __name__ == "__main__":
    raise SystemExit(run_cli(entry_script=Path(__file__).resolve()))
