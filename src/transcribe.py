"""Audio transcription via Groq Whisper API."""

from __future__ import annotations

from time import sleep
from typing import Any

from groq import Groq, RateLimitError

from src.config import groq_api_key

WHISPER_MODEL = "whisper-large-v3"
MAX_AUDIO_BYTES = 25 * 1024 * 1024  # provider limit


def _client() -> Groq:
    key = groq_api_key()
    if not key:
        raise RuntimeError("GROQ_API_KEY missing (.env)")
    return Groq(api_key=key)


def transcribe(audio_bytes: bytes, filename: str = "audio.webm") -> dict[str, Any]:
    """Returns {'transcript': str, 'language': detected-language-code}."""
    if len(audio_bytes) == 0:
        raise ValueError("empty audio file")
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise ValueError("audio file exceeds 25 MB limit")

    delay = 1.0
    for attempt in range(6):
        try:
            out = _client().audio.transcriptions.create(
                model=WHISPER_MODEL,
                file=(filename, audio_bytes),
                response_format="verbose_json",
            )
            break
        except RateLimitError:
            if attempt == 5:
                raise
            sleep(delay)
            delay = min(delay * 2, 30.0)

    text = (getattr(out, "text", "") or "").strip()
    language = getattr(out, "language", None)
    return {"transcript": text, "language": language}
