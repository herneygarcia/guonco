# User Stories — GuOnco Registry

Persona: urologist seeing genitourinary oncology patients in office.
Goal: register each patient in under 2 minutes, by voice, with review before
anything is saved.

## Core daily workflow

**US1 — Select pathology**
As the physician, after greeting a patient I tap one of 9 pathology buttons
(próstata, vejiga, riñón, testículo, pene, uréter/urotelial alto, adrenal,
escroto, uretra). Each button shows the pathology name and CIE-10 code.
*Acceptance:* form for that pathology renders instantly; last-used pathology
is preselected on reopen.

**US2 — Dictate**
I press the mic button and dictate naturally in Spanish or English
("Varón de 68 años, PSA doce, Gleason siete más cuatro más tres...").
Press again to stop. The app sends audio to Groq Whisper and shows the
transcript. *Acceptance:* works from laptop browser AND phone (PWA over
Wi-Fi); transcript editable by hand; total wait < 10 s typical.

**US3 — Review extracted variables**
The AI maps my dictation onto the pathology's variables. Every field shows a
dual label `es / en` (e.g., "PSA al diagnóstico / PSA at diagnosis") with the
extracted value pre-filled; unstated fields are empty. Fields I didn't mention
never block saving. *Acceptance:* select fields only ever contain valid
dictionary codes; values not stated appear as blank, never invented.

**US4 — Correct and save**
I fix anything wrong (dropdowns, typing), then tap Save. Record goes to local
SQLite with status "pending sync". *Acceptance:* save < 1 s; validation
rejects impossible values (422) with a clear bilingual message; record
retrievable by historia_clinica.

## Data management

**US5 — Automatic backup to Google Sheets/Drive**
When I have Wi-Fi at end of day (or manually), tapping Sync pushes all pending
records to Google Sheets — one sheet per pathology — via Apps Script.
Failures leave records pending; nothing is ever lost locally.
*Acceptance:* upsert by _id (re-sync doesn't duplicate); sync status visible
per record; works offline (queued).

**US6 — Export for analysis**
One click downloads .xlsx with one sheet per pathology, bilingual column
headers "es / en". *Acceptance:* opens correctly in Excel/Sheets; dates are
dates, numbers are numbers.

**US7 — Bilingual display**
Every label renders both languages simultaneously ("Edad al diagnóstico /
Age at diagnosis"). No toggle needed. Stored data is language-neutral codes,
so an English-speaking colleague reads the same database without migration.

## Non-functional requirements

- NFR1: No patient data leaves the machine except: audio chunk → Groq
  (transcription), extracted text → Groq LLM, saved records → user's own
  Google Sheets when Sync is pressed.
- NFR2: API keys live in `.env`, never committed, never logged.
- NFR3: App usable on phone browser (responsive, large touch targets).
- NFR4: Extraction accuracy ≥90% per-field on harness golden cases before any
  prompt/model change ships.
- NFR5: Full registration flow (US1→US4) achievable in under 2 minutes.
