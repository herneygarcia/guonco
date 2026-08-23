"""FastAPI application — GuOnco Registry backend (specs/api_contract.md)."""

from __future__ import annotations

import contextlib
import pathlib
from typing import Any

from fastapi import Body, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from src import auth as auth_mod
from src import export, schema, store, validation
from src import sync as sync_mod
from src.config import (
    app_pins,
    apps_script_url,
    groq_api_key,
    session_secret,
    store_mode,
)
from src.db import init_db

ROOT = pathlib.Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"

PUBLIC_API_PATHS = {"/api/login", "/api/session", "/api/logout"}


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="GuOnco Registry", version=schema.META["version"], lifespan=lifespan
)


@app.middleware("http")
async def auth_gate(request: Request, call_next):
    """When APP_PINS is configured, every /api call needs a session cookie;
    write methods additionally require an rw (writer) role."""
    path = request.url.path
    if app_pins() and path.startswith("/api/") and path not in PUBLIC_API_PATHS:
        secret = session_secret()
        token = request.cookies.get(auth_mod.COOKIE_NAME)
        session = auth_mod.verify_token(token, secret) if token and secret else None
        if session is None:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        username, role = session
        request.state.user = username
        request.state.role = role
        if request.method in ("POST", "PUT", "DELETE") and role != "rw":
            return JSONResponse(
                {"error": "forbidden", "detail": "read-only account"},
                status_code=403,
            )
    return await call_next(request)


def _actor(request: Request) -> str | None:
    return getattr(request.state, "user", None)


def _http_error(status: int, error: str, **detail: Any) -> JSONResponse:
    return JSONResponse({"error": error, "detail": detail}, status_code=status)


# ---------------------------------------------------------------- health ----
@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "db": (records_counts_safe()) is not None,
        "groq_key_present": bool(groq_api_key()),
        "apps_script_url_present": bool(apps_script_url()),
        "store": store_mode(),
        "auth_enabled": bool(app_pins()),
    }


def records_counts_safe():
    try:
        return store.counts_by_status()
    except Exception:
        return None


# ------------------------------------------------------------------- auth ---
@app.post("/api/login")
def login(payload: dict = Body(...)) -> Response:
    session = auth_mod.authenticate(payload.get("code", ""))
    if session is None:
        raise HTTPException(401, "código inválido / invalid code")
    username, role = session
    token = auth_mod.create_token(username, session_secret() or "guonco")
    response = JSONResponse({"user": username, "role": role})
    response.set_cookie(
        auth_mod.COOKIE_NAME,
        token,
        max_age=auth_mod.SESSION_TTL_S,
        httponly=True,
        samesite="lax",
    )
    return response


@app.get("/api/session")
def session_info(request: Request) -> dict:
    if not app_pins():
        return {"enabled": False, "user": None, "role": None}
    secret = session_secret()
    token = request.cookies.get(auth_mod.COOKIE_NAME)
    session = auth_mod.verify_token(token, secret) if token and secret else None
    return {
        "enabled": True,
        "user": session[0] if session else None,
        "role": session[1] if session else None,
    }


@app.post("/api/logout")
def logout() -> Response:
    response = JSONResponse({"ok": True})
    response.delete_cookie(auth_mod.COOKIE_NAME)
    return response


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
    return {"key": key, **schema.PATHOLOGIES[key]}


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
def create_record(request: Request, payload: dict = Body(...)) -> dict:
    key = payload.get("pathology", "")
    fields = payload.get("fields") or {}
    if key not in schema.PATHOLOGIES:
        raise HTTPException(404, f"unknown pathology '{key}'")
    try:
        return store.save_record(
            key, fields, record_id=payload.get("_id") or None, actor=_actor(request)
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
    items, total = store.list_records(
        pathology_key=pathology, status=status, limit=limit, offset=offset
    )
    return {"records": items, "total": total}


@app.get("/api/records/{record_id}")
def get_one(record_id: str) -> dict:
    rec = store.get_record(record_id)
    if rec is None:
        raise HTTPException(404, "record not found")
    return rec


@app.put("/api/records/{record_id}")
def update_one(
    record_id: str, request: Request, payload: dict = Body(...)
) -> dict:
    existing = store.get_record(record_id)
    if existing is None:
        raise HTTPException(404, "record not found")
    merged = {**existing["fields"], **(payload.get("fields") or {})}
    try:
        return store.save_record(
            existing["_patologia"], merged, record_id, actor=_actor(request)
        )
    except validation.ValidationFailure as exc:
        return _http_error(422, "validation failed", errors=exc.errors)


@app.delete("/api/records/{record_id}")
def delete_one(record_id: str) -> dict:
    if not store.delete_record(record_id):
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
    counts = store.counts_by_status()
    counts["apps_script_configured"] = bool(apps_script_url())
    counts["store"] = store_mode()
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
