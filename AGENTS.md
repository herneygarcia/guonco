# AGENTS.md

Guidance for any AI coding assistant working on this repository.

## Project

GuOnco Registry — voice-driven GU oncology patient registry.
Python (FastAPI + SQLite) backend, PWA frontend, Groq Whisper transcription,
Groq LLM extraction, Google Sheets backup via Apps Script. Bilingual ES/EN.

## Source of truth

- `specs/data_dictionary.yaml` defines ALL clinical variables. Never hard-code
  field ids, labels, or option values anywhere else.
- `src/schema.py` is GENERATED from the YAML. Do not hand-edit it — change the
  YAML and regenerate.
- Fields marked `auto: today` in the dictionary are filled automatically by
  the server (and prefilled in the UI) when omitted; an explicit value wins.
  Do not add other hard-coded auto-fill logic.
- Specs (`specs/*.md`) govern behavior. If code and spec disagree, fix the code
  or propose a spec change explicitly.

## Language rules

- Stored values must be language-neutral CODES (e.g. `ALTO_GRADO`), never
  display strings. Display strings come only from dictionary labels.
- UI always renders dual labels `label_es / label_en`.

## Before you consider any change done

1. `pytest` passes (add/adjust tests for behavior changes).
2. If you touched extraction prompts, models, or dictionary option values:
   run `.venv/bin/python harness/run_eval.py` and report the score.
   Gate: ≥90% per-field accuracy on golden cases. Below gate = do not ship;
   iterate or flag for human review.
3. No secrets in code, logs, or tests. Keys come from `.env` only.
4. No patient data fixtures with real identifiers; synthetic data only.

## Conventions

- Python: stdlib typing, Pydantic v2 models for validation, ruff-clean.
- Frontend: no build step; vanilla JS modules served by FastAPI static files.
- Commits: imperative mood, reference spec section when behavior changes
  (e.g. "extract: map Gleason spoken patterns (spec/extraction_spec.md)").

## Adding a variable or pathology

Edit `specs/data_dictionary.yaml` → regenerate schema → add golden cases for
any new select options → update tests. A pathology entry automatically gets a
SQLite table, UI button, sheet, and export tab.
