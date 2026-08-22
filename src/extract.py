"""LLM extraction: free-text dictation (es/en) -> data-dictionary field codes.

Rules per specs/extraction_spec.md:
- Only fields defined for the pathology may be returned; values must be
  language-neutral CODES for selects.
- Unstated information is null — never invented.
- Server-side validation drops any value that violates the dictionary and
  reports it in `unmapped_notes` (defense against hallucination).
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from groq import Groq, RateLimitError

from src import schema
from src.config import groq_api_key
from src.validation import coerce_value

DEFAULT_MODEL = "openai/gpt-oss-120b"


def _model() -> str:
    return os.environ.get("GROQ_EXTRACT_MODEL", DEFAULT_MODEL)

SYSTEM_PROMPT = """\
You are a medical data extraction engine for a genitourinary oncology \
registry. You receive a dictated clinical note (Spanish or English) and a \
list of allowed variables with their allowed option codes.

Return ONLY a JSON object:
  {"fields": {"<field_id>": <value>, ...}, "notes": ["..."]}

Hard rules:
1. Use exactly the field_ids provided. No other keys.
2. For select fields, output the exact option CODE string, copied \
character-for-character from the list (e.g. if the options include 7_4+3, \
write exactly "7_4+3"). Never reformat, translate, or paraphrase codes.
3. Numbers as plain numbers ("PSA de doce" -> 12). Dates as YYYY-MM-DD.
4. If a variable is not explicitly stated, OMIT it entirely. Never guess, \
never infer beyond what was said.
5. Negations matter: "sin metástasis" -> M0 only if staging is clearly stated.
6. When ONE tumor is described with MULTIPLE histological subtypes, choose \
the mixed/combined option of the histologia field (e.g. "tumor mixto de \
células germinales") rather than a single subtype.
7. When several events/statuses over time are mentioned (e.g. "recurrencia \
local, luego perdido para el control"), estado_actual reflects the MOST \
RECENT one.
8. notes: mention dictation fragments you could not map to any variable.\
"""


def build_user_prompt(pathology_key: str) -> str:
    spec = schema.PATHOLOGIES[pathology_key]
    lines = [f"PATHOLOGY: {spec['nombre_en']} ({spec['cie10']})", "", "VARIABLES:"]
    for f in spec["fields"]:
        desc = f"{f['id']} [{f['type']}] {f['label_es']} / {f['label_en']}"
        if f["type"] == "select":
            opts = ", ".join(
                f"{o['code']}({o.get('es', o['code'])})" for o in f.get("options", [])
            )
            desc += f" options: {opts}"
        if f.get("unit"):
            desc += f" unit={f['unit']}"
        lines.append(f"- {desc}")
    return "\n".join(lines)


def _client() -> Groq:
    key = groq_api_key()
    if not key:
        raise RuntimeError(
            "GROQ_API_KEY missing. Create a .env file in the project root "
            "(copy .env.example) and set your key."
        )
    return Groq(api_key=key)


def _create_with_retry(client: Groq, **kwargs: Any) -> Any:
    delay = 1.0
    for attempt in range(6):
        try:
            return client.chat.completions.create(**kwargs)
        except RateLimitError:
            if attempt == 5:
                raise
            time.sleep(delay)  # free tier TPM limit; back off and retry
            delay = min(delay * 2, 30.0)


def extract_fields(pathology_key: str, transcript: str) -> dict[str, Any]:
    if pathology_key not in schema.PATHOLOGIES:
        raise KeyError(f"unknown pathology '{pathology_key}'")

    completion = _create_with_retry(
        _client(),
        model=_model(),
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": build_user_prompt(pathology_key)
                + f"\n\nDICTATION:\n\"\"\"{transcript}\"\"\"",
            },
        ],
    )
    raw = json.loads(completion.choices[0].message.content or "{}")
    candidate: dict[str, Any] = raw.get("fields", {})
    notes: list[str] = list(raw.get("notes", []) or [])

    fmap = {f["id"]: f for f in schema.PATHOLOGIES[pathology_key]["fields"]}
    cleaned: dict[str, Any] = {}
    for fid, value in candidate.items():
        if fid not in fmap or value is None or value == "":
            continue
        try:
            cleaned[fid] = coerce_value(fmap[fid], value)
        except ValueError:
            notes.append(
                f"dropped '{fid}': invalid value {value!r} for this registry"
            )

    unmapped = [n for n in notes if n]
    return {"fields": cleaned, "unmapped_notes": unmapped}
