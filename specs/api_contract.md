# API Contract — GuOnco Registry

Base URL: `http://localhost:8000` (also reachable at `http://<lan-ip>:8000`
from phone). All request/response bodies are JSON unless noted.

Error convention: `{ "error": "<message>", "detail": {...} }` with proper HTTP
status codes (400 bad request, 404 unknown id, 422 validation failure, 502
upstream provider failure).

## Health

### GET /health
```json
{ "status": "ok", "db": true, "groq_key_present": true, "apps_script_url_present": false }
```

## Auth

Login is required when `APP_PINS` and/or `GOOGLE_USERS` is set. Every other
`/api/*` call then needs the `guonco_session` cookie (401 otherwise); POST/PUT/
DELETE also need the `rw` role (403 for `ro`). Sessions last 12 h and end
immediately when the user is removed from the list.

### GET /api/session
```json
{ "enabled": true, "user": "doctor@example.org", "role": "rw",
  "pin_enabled": true, "google_client_id": "123-abc.apps.googleusercontent.com" }
```
`{ "enabled": false, "user": null, "role": null }` when auth is off.
`google_client_id` is `null` when Google sign-in is not configured.

### POST /api/login
`{ "code": "1234" }` → `{ "user": "herney", "role": "rw" }` + session cookie; 401 on a bad code.

### POST /api/login/google
`{ "credential": "<Google Identity Services ID token>" }` →
`{ "user": "<email, lowercased>", "role": "rw"|"ro" }` + session cookie.
The server verifies signature, audience (`GOOGLE_CLIENT_ID`), issuer, expiry
and `email_verified`; 401 if any check fails or the email is not in `GOOGLE_USERS`.

### POST /api/logout
Clears the session cookie.

## Dictionary

### GET /api/pathologies
List all pathologies from the data dictionary.
```json
{ "pathologies": [ { "key": "prostata", "nombre_es": "Cáncer de Próstata",
    "nombre_en": "Prostate Cancer", "cie10": "C61", "color": "#2980b9",
    "field_count": 30 } ] }
```

### GET /api/pathologies/{key}/fields
Full field list (labels es/en, options with codes) for form rendering.
Returns 404 if `key` not in dictionary.

## Voice & extraction

### POST /api/transcribe   (multipart/form-data: file=audio.webm|wav)
Groq Whisper `whisper-large-v3`. Language auto-detected (es/en).
```json
{ "transcript": "Varón de 68 años, PSA doce...", "language": "es" }
```

### POST /api/extract
```json
{ "pathology": "prostata", "transcript": "Varón de 68 años, PSA 12, Gleason 7 más 4 más 3..." }
```
Response — keys are field IDs from dictionary; values are option CODES for
selects, raw values for number/date/text, null when unstated:
```json
{
  "fields": {
    "edad": 68, "sexo": "MASCULINO",
    "psa_diagnostico": 12, "gleason": "7_4+3",
    "histologia": null, "tnm_m": null
  },
  "unmapped_notes": ["menciona 'tocamiento endurecido' sin variable asociada"]
}
```
Server-side validation guarantees every returned key exists in the dictionary
for that pathology and every select value is an allowed code; violations are
dropped (not stored) and reported in `unmapped_notes`.

## Records

### POST /api/records
```json
{ "pathology": "vejiga",
  "fields": { "historia_clinica": "HC-123", "grado_who": "ALTO_GRADO", "...": null },
  "_id": "optional-client-generated-uuid" }
```
Response: full saved record incl. server-assigned `_id` (if omitted),
timestamps and `"sync_status": "pending"`. Upsert semantics on `_id`.
Fields marked `auto: today` in the dictionary (currently `fecha_registro`)
are filled with today's date when omitted or empty; an explicit value
always wins.
Validation: 422 if any field id/value violates the dictionary.

### GET /api/records?pathology=vejiga&limit=50&offset=0&status=pending
```json
{ "records": [ { "_id": "...", "_patologia": "vejiga", "_created_at": "...",
                 "_updated_at": "...", "_sync_status": "pending", "fields": {...} } ],
  "total": 42 }
```

### GET /api/records/{id} · PUT /api/records/{id} · DELETE /api/records/{id}

## Sync

### POST /api/sync
Pushes all `pending` records to the configured Apps Script web app
(doPost upsert-by-_id, one sheet per pathology). Marks records `synced` on
success; leaves them `pending` on failure.

### GET /api/sync/status
```json
{ "pending": 3, "synced": 139, "last_sync_at": "2026-08-21T14:03:00Z",
  "apps_script_configured": true }
```

## Export

### GET /api/export.xlsx?pathology=prostata   (omit for all pathologies)
Binary xlsx; one sheet per pathology, headers `<es> / <en>`, rows ordered by
creation date. `Content-Disposition: attachment`.

## Configuration endpoints (local only)

### GET/PUT /api/config
Reads/writes `.env`-backed settings: `GROQ_API_KEY` (write-only, never
returned), `APPS_SCRIPT_URL`. Never logged.
