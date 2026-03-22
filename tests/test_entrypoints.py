from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"


def _read_script(name: str) -> str:
    return (SCRIPTS_DIR / name).read_text(encoding="utf-8")


def test_send_message_entrypoint_stays_thin_wrapper() -> None:
    assert _read_script("send_message.py") == """#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from openclaw_feishu_cron_kit.core import run_cli


if __name__ == "__main__":
    raise SystemExit(run_cli(entry_script=Path(__file__).resolve()))
"""


def test_sync_openclaw_jobs_entrypoint_stays_thin_wrapper() -> None:
    assert _read_script("sync_openclaw_jobs.py") == """#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from openclaw_feishu_cron_kit.jobs_sync import run_cli


if __name__ == "__main__":
    raise SystemExit(run_cli())
"""


def test_process_retry_queue_entrypoint_stays_thin_wrapper() -> None:
    assert _read_script("process_retry_queue.py") == """#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from openclaw_feishu_cron_kit.core import run_cli


if __name__ == "__main__":
    raise SystemExit(run_cli(["--mode", "retry-pending"], entry_script=ROOT / "scripts" / "send_message.py"))
"""


def test_upsert_ai_hotspot_bitable_entrypoint_stays_thin_wrapper() -> None:
    assert _read_script("upsert_ai_hotspot_bitable.py") == """#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from openclaw_feishu_cron_kit.ai_hotspot_bitable import run_cli


if __name__ == "__main__":
    raise SystemExit(run_cli(entry_script=Path(__file__).resolve()))
"""
