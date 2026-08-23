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


def app_pins() -> dict[str, dict[str, str]]:
    """Parse APP_PINS env var -> {name: {"pin": str, "role": "rw"|"ro"}}.

    Format: "name:pin[,name:pin[:ro]]..."  Empty/unset means auth disabled.
    """
    load_env()
    raw = os.environ.get("APP_PINS", "").strip()
    users: dict[str, dict[str, str]] = {}
    if not raw:
        return users
    for entry in raw.split(","):
        parts = [p.strip() for p in entry.split(":")]
        if len(parts) < 2 or not parts[0] or not parts[1]:
            continue
        role = "ro" if "ro" in parts[2:] else "rw"
        users[parts[0]] = {"pin": parts[1], "role": role}
    return users


def session_secret() -> str | None:
    """SESSION_SECRET, or one deterministically derived from APP_PINS."""
    import hashlib

    load_env()
    secret = os.environ.get("SESSION_SECRET", "").strip()
    if secret:
        return secret
    pins = os.environ.get("APP_PINS", "").strip()
    if pins:
        return "derived:" + hashlib.sha256(pins.encode("utf-8")).hexdigest()
    return None


def script_secret() -> str | None:
    """Shared secret sent to the Apps Script web app (SCRIPT_SECRET)."""
    load_env()
    secret = os.environ.get("SCRIPT_SECRET", "").strip()
    return secret or None


def store_mode() -> str:
    """'sqlite' (default) or 'sheets' — Google Sheets as source of truth."""
    load_env()
    mode = os.environ.get("STORE", "sqlite").strip().lower()
    return mode if mode in ("sqlite", "sheets") else "sqlite"
