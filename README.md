# GuOnco Registry — Registro GU Onco

Voice-driven patient registry for genitourinary oncology. Dictate after each
visit (Spanish or English), the app transcribes, extracts the clinical
variables, you review and save. Data lives in local SQLite; one click backs it
up to your own Google Sheets/Drive. Every label is bilingual ES/EN; stored
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
spreadsheet, paste the script, deploy as web app, put the `/exec` URL in
`.env` as `APPS_SCRIPT_URL`.

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
                 ├─ /api/transcribe → Groq whisper-large-v3
                 ├─ /api/extract    → Groq LLM → dictionary codes
                 ├─ SQLite (data/guonco.sqlite)   ← source of truth
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
