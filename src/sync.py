"""Google Sheets sync via Apps Script web app (doPost upsert-by-_id)."""

from __future__ import annotations

from typing import Any

import httpx

from src import records, schema
from src.config import apps_script_url

TIMEOUT_S = 60


def build_sync_payload(record_dicts: list[dict[str, Any]]) -> dict[str, Any]:
    """Shape expected by the generated Apps Script (scripts/setup_apps_script.py):
    one entry per pathology with bilingual column headers and code rows."""
    by_pathology: dict[str, list[dict]] = {}
    for r in record_dicts:
        by_pathology.setdefault(r["_patologia"], []).append(r)

    campos = {}
    for key, recs in by_pathology.items():
        fields = schema.PATHOLOGIES[key]["fields"]
        headers = ["_id"] + [
            f"{f['label_es']} / {f['label_en']}" for f in fields
        ]
        codes = ["_id"] + [f["id"] for f in fields]
        rows = []
        for r in recs:
            rows.append(
                [r["_id"]]
                + [
                    _display(r["fields"].get(f["id"]), f)
                    for f in fields
                ]
            )
        campos[key] = {"headers": headers, "codes": codes, "rows": rows}
    return {"registros_por_patologia": campos}


def _display(value: Any, field: dict) -> Any:
    """Sheets are human-readable: show 'es' label next to the stored CODE."""
    if value is None:
        return ""
    if field["type"] == "boolean":
        es = "Sí" if value else "No"
        en = "Yes" if value else "No"
        return f"{int(value)} ({es}/{en})"
    if field["type"] == "select":
        for o in field.get("options", []):
            if o["code"] == value:
                es = o.get("es", value)
                en = o.get("en", value)
                return value if es == en else f"{value} ({es}/{en})"
        return str(value)
    return value


def sync_pending() -> dict[str, Any]:
    url = apps_script_url()
    if not url:
        raise RuntimeError("APPS_SCRIPT_URL not configured (.env)")

    pending, _total = records.list_records(status="pending", limit=10_000)
    if not pending:
        return {"synced": 0, "message": "nothing to sync"}

    payload = build_sync_payload(pending)
    # Apps Script answers with a 302 to script.googleusercontent.com — follow it
    response = httpx.post(url, json=payload, timeout=TIMEOUT_S, follow_redirects=True)
    response.raise_for_status()
    result = response.json()
    if not result.get("ok"):
        raise RuntimeError(f"Apps Script error: {result}")

    synced_ids = [r["_id"] for r in pending]
    records.mark_synced(synced_ids)
    return {"synced": len(synced_ids), "ids": synced_ids}
