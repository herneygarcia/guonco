# GuOnco Registry — Registro GU Onco

Voice-driven patient registry for genitourinary oncology. Dictate after each
visit (Spanish or English), the app transcribes, extracts the clinical
variables, you review and save. Every label is bilingual ES/EN; stored
values are language-neutral codes.

Built spec-first: `specs/data_dictionary.yaml` is the single source of truth
for all 9 pathologies (próstata, vejiga, riñón, testículo, pene, uréter,
adrenal, escroto, uretra) — it generates the database schema, the UI forms,
the AI prompt constraints, validation, and the Sheets columns.

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env        # add your Groq API key
make run                    # → http://localhost:8000
```

Open in **Chrome** (microphone access). From your phone on the same Wi-Fi:
`http://<your-mac-ip>:8000` — or anywhere via Tailscale. In Chrome mobile,
use *Add to Home Screen* to install it like an app.

## Start / stop (every session)

**Start**

```bash
cd ~/Downloads/04_Clinical_Urology/gu_onco   # the project folder
source .venv/bin/activate                     # prompt shows (.venv)
make run                                      # → http://localhost:8000
```

`make run` uses `.venv/bin/...` directly, so activating is optional — it just
lets you type `pytest`, `python`, etc. without the `.venv/bin/` prefix.

**Stop**

1. In the terminal running the server press **Ctrl+C** — localhost:8000 is
   now off.
2. Leave the virtual environment: `deactivate` (the `(.venv)` prefix
   disappears).

If the terminal was closed and port 8000 is still busy
(`address already in use`):

```bash
lsof -ti :8000 | xargs kill
```

## Daily use

1. Tap a pathology chip.
2. Tap the mic, dictate naturally ("Varón de 68 años, PSA doce, Gleason siete
   más cuatro más tres…"), tap again to stop.
3. Review the extracted form (unstated fields stay empty), correct anything.
4. **Guardar paciente** — saved locally with status *pending*.
5. End of day: **Sincronizar** pushes everything to Google Sheets.

Nothing leaves your machine except: audio → Groq Whisper, transcript → Groq
LLM, saved records → your own spreadsheet when you press sync.

## Setup for Sheets backup

```bash
make apps-script            # generates scripts/apps_script/Code.gs
```

Then follow `scripts/apps_script/INSTRUCTIONS.md` (~5 min): create a blank
spreadsheet, paste the script, **set your `SCRIPT_SECRET`** in both the
script and `.env`, deploy as web app, put the `/exec` URL in `.env` as
`APPS_SCRIPT_URL`.

## Logins & roles (multi-user)

Add per-user PINs in `.env` to require login and attribute each record:

```
APP_PINS=herney:1234,carla:5678,estudiante:9999:ro
```

- `name:pin` — writer: can save/edit/delete; every record is stamped with
  their name (`registrado_por` column in Sheets).
- `name:pin:ro` — read-only: can browse and export but not save.
- Leave empty for single-user local use without login.

### Google login (optional, alongside PINs)

1. [Google Cloud Console](https://console.cloud.google.com/apis/credentials) →
   **Create credentials → OAuth client ID → Web application**.
2. **Authorized JavaScript origins**: `http://localhost:8000` and your Render
   URL (e.g. `https://guonco.onrender.com`). No redirect URI is needed.
3. Put the client ID and the allowed accounts in `.env` (and in the Render
   dashboard):

```
GOOGLE_CLIENT_ID=1234567890-abc.apps.googleusercontent.com
GOOGLE_USERS=doctor@example.org,student@example.org:ro
```

- `email` — writer; `email:ro` — read-only. Records are stamped with the email.
- Only listed accounts get in; anyone else is rejected even with a valid Google login.
- Removing an email logs that person out immediately.
- With `GOOGLE_USERS` set and `APP_PINS` empty, the login screen shows only the Google button.

## Google Sheets as source of truth (optional)

Set in `.env`:

```
STORE=sheets
SCRIPT_SECRET=<same secret as Code.gs>
APPS_SCRIPT_URL=https://script.google.com/macros/s/XXXX/exec
```

Saves go straight to your spreadsheet; SQLite remains an automatic offline
cache (failed writes queue locally and retry via **Sincronizar**). To move
existing local records into Sheets once: `.venv/bin/python
scripts/migrate_sqlite_to_sheets.py`.

## Commands

| Command | What it does |
|---|---|
| `make run` | start server at :8000 |
| `make test` | pytest suite |
| `make eval` | extraction accuracy vs golden cases (gate ≥90%) |
| `make schema` | regenerate `src/schema.py` from the YAML dictionary |
| `make apps-script` | regenerate Apps Script backend |

## Architecture

```
Browser/PWA ──► FastAPI (src/main.py)
                 ├─ /api/login      → per-user PIN sessions (rw / ro)
                 ├─ /api/transcribe → Groq whisper-large-v3
                 ├─ /api/extract    → Groq LLM → dictionary codes
                 ├─ store (src/store.py)
                 │    ├─ STORE=sqlite → SQLite source of truth
                 │    └─ STORE=sheets → Sheets first, SQLite offline cache
                 ├─ /api/sync       → Apps Script → Google Sheets
                 └─ /api/export.xlsx
```

- Specs: `specs/` (dictionary, user stories, API contract)
- Harness: `harness/golden_cases.yaml` + `run_eval.py` — every prompt/model/
  dictionary change must keep per-field accuracy ≥90% before shipping.
- Conventions for AI assistants: see `AGENTS.md`.

## Privacy

- API keys live only in `.env` (gitignored).
- Patient data lives only in `data/guonco.sqlite` (gitignored) and your own
  Google Sheet.
- Golden-case dictations are synthetic; no real patient identifiers anywhere
  in the repo.
