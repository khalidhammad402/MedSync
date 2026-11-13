"""Central configuration. Reads optional values from the environment or a .env file."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FOOTER = "SYNTHETIC DEMO DATA – NOT FOR CLINICAL USE"
DISPENSING_WINDOW_DAYS = 120   # a dispensing record this recent is treated as ground truth
ROTATION_WARN_DAYS = 30        # R1: contract rotates within this many days
DOUBLE_PACK_DAYS = 90          # R3: old and new packs may both be at home


def _load_dotenv() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


def db_path() -> str:
    return os.environ.get("MEDSYNC_DB", str(ROOT / "medsync.db"))


def today() -> date:
    fixed = os.environ.get("MEDSYNC_TODAY", "").strip()
    return date.fromisoformat(fixed) if fixed else date.today()


def use_llm() -> bool:
    return os.environ.get("USE_LLM_EXTRACTOR", "false").strip().lower() in ("1", "true", "yes")


def aws_region() -> str:
    return os.environ.get("AWS_REGION", "eu-central-1")


def bedrock_model_id() -> str:
    return os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-opus-5-5")
