"""Load .env from project root into os.environ (never logs secret values)."""

from __future__ import annotations

import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"


def load_env() -> dict[str, str]:
    loaded: dict[str, str] = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key and value:
                loaded[key] = value
                os.environ.setdefault(key, value)
    return loaded


def groq_api_key() -> str | None:
    load_env()
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if not key or key.startswith("gsk_your"):
        return None
    return key


def apps_script_url() -> str | None:
    load_env()
    url = os.environ.get("APPS_SCRIPT_URL", "").strip()
    return url or None
