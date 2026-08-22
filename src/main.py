"""FastAPI application — GuOnco Registry backend (specs/api_contract.md)."""

from __future__ import annotations

import pathlib
from typing import Any

from fastapi import Body, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from src import export, records, schema, validation
from src import sync as sync_mod
from src.config import apps_script_url, groq_api_key

ROOT = pathlib.Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"

app = FastAPI(title="GuOnco Registry", version=schema.META["version"])


def _http_error(status: int, error: str, **detail: Any) -> JSONResponse:
    return JSONResponse({"error": error, "detail": detail}, status_code=status)


# ---------------------------------------------------------------- health ----
@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "db": (records.counts_by_status()) is not None,
        "groq_key_present": bool(groq_api_key()),
        "apps_script_url_present": bool(apps_script_url()),
    }


# ------------------------------------------------------------ dictionary ----
@app.get("/api/pathologies")
def pathologies() -> dict:
    out = []
    for key, spec in schema.PATHOLOGIES.items():
        out.append(
            {
                "key": key,
                "nombre_es": spec["nombre_es"],
                "nombre_en": spec["nombre_en"],
                "cie10": spec["cie10"],
                "color": spec["color"],
                "field_count": len(spec["fields"]),
            }
        )
    return {"pathologies": out}


@app.get("/api/pathologies/{key}/fields")
def pathology_fields(key: str) -> dict:
    if key not in schema.PATHOLOGIES:
        raise HTTPException(404, f"unknown pathology '{key}'")
    return schema.PATHOLOGIES[key]


# ------------------------------------------------------- voice/extract ------
@app.post("/api/transcribe")
async def transcribe(file: UploadFile = File(...)) -> dict:
    from src.transcribe import transcribe as whisper_transcribe

    audio = await file.read()
    try:
        return whisper_transcribe(audio, filename=file.filename or "audio.webm")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from None


@app.post("/api/extract")
def extract(payload: dict = Body(...)) -> dict:
    from src.extract import extract_fields

    key = payload.get("pathology", "")
    transcript = payload.get("transcript", "").strip()
    if key not in schema.PATHOLOGIES:
        raise HTTPException(404, f"unknown pathology '{key}'")
    if not transcript:
        raise HTTPException(400, "transcript is empty")
    try:
        return extract_fields(key, transcript)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from None


# ---------------------------------------------------------------- records ---
@app.post("/api/records")
def create_record(payload: dict = Body(...)) -> dict:
    key = payload.get("pathology", "")
    fields = payload.get("fields") or {}
    if key not in schema.PATHOLOGIES:
        raise HTTPException(404, f"unknown pathology '{key}'")
    try:
        return records.save_record(
            key, fields, record_id=payload.get("_id") or None
        )
    except validation.ValidationFailure as exc:
        return _http_error(422, "validation failed", errors=exc.errors)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from None


@app.get("/api/records")
def list_all(
    pathology: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    if pathology and pathology not in schema.PATHOLOGIES:
        raise HTTPException(404, f"unknown pathology '{pathology}'")
    items, total = records.list_records(
        pathology_key=pathology, status=status, limit=limit, offset=offset
    )
    return {"records": items, "total": total}


@app.get("/api/records/{record_id}")
def get_one(record_id: str) -> dict:
    rec = records.get_record(record_id)
    if rec is None:
        raise HTTPException(404, "record not found")
    return rec


@app.put("/api/records/{record_id}")
def update_one(record_id: str, payload: dict = Body(...)) -> dict:
    existing = records.get_record(record_id)
    if existing is None:
        raise HTTPException(404, "record not found")
    merged = {**existing["fields"], **(payload.get("fields") or {})}
    try:
        return records.save_record(existing["_patologia"], merged, record_id)
    except validation.ValidationFailure as exc:
        return _http_error(422, "validation failed", errors=exc.errors)


@app.delete("/api/records/{record_id}")
def delete_one(record_id: str) -> dict:
    if not records.delete_record(record_id):
        raise HTTPException(404, "record not found")
    return {"deleted": record_id}


# ------------------------------------------------------------------- sync ---
@app.post("/api/sync")
def do_sync() -> dict:
    try:
        return sync_mod.sync_pending()
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from None


@app.get("/api/sync/status")
def sync_status() -> dict:
    counts = records.counts_by_status()
    counts["apps_script_configured"] = bool(apps_script_url())
    return counts


# ----------------------------------------------------------------- export ---
@app.get("/api/export.xlsx")
def export_xlsx(pathology: str | None = None) -> Response:
    try:
        data = export.export_xlsx(pathology)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from None
    return Response(
        content=data,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={"Content-Disposition": 'attachment; filename="guonco.xlsx"'},
    )


# ------------------------------------------------------------------ static --
if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
