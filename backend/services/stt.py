"""Ovoz → matn (speech-to-text) — OpenAI-mos `/audio/transcriptions` endpoint.

Groq (whisper-large-v3-turbo) yoki OpenAI (gpt-4o-mini-transcribe) — ikkalasi
bir xil so'rov formatini qabul qiladi, shuning uchun provayder faqat .env
orqali almashadi (STT_BASE_URL / STT_MODEL / STT_API_KEY).

Claude audio qabul qilmaydi — shuning uchun alohida STT qatlami. Mikrofondan
kelgan webm/mp4/ogg to'g'ridan-to'g'ri yuboriladi (konvertatsiya yo'q).
"""

from __future__ import annotations

import logging

import httpx

from config import settings

log = logging.getLogger(__name__)

MAX_AUDIO_BYTES = 3 * 1024 * 1024  # 3 MB ≈ 20-25 soniya opus/aac
TIMEOUT = 25.0

# Whisper'ga til/uslub «langar»i: arab yozuvi, fusha. Prompt kontekst beradi,
# lekin mazmunni «taklif qilmaydi» — talaffuz bahosida ham xolis qoladi.
NEUTRAL_PROMPT = "الكلام التالي باللغة العربية."


def available() -> bool:
    return bool(settings.stt_api_key)


async def transcribe(
    audio: bytes, filename: str = "speech.webm", mime: str = "audio/webm", prompt: str = ""
) -> str:
    """Audio baytlarni arabcha matnga aylantiradi. Xatoda bo'sh satr."""
    if not available():
        return ""
    if not audio or len(audio) > MAX_AUDIO_BYTES:
        return ""

    url = settings.stt_base_url.rstrip("/") + "/audio/transcriptions"
    data = {
        "model": settings.stt_model,
        "language": "ar",
        "response_format": "json",
        "temperature": "0",
        # Prompt: mavzu konteksti (oxirgi ustoz savoli) + arab yozuvi langari
        "prompt": (prompt.strip() + " " + NEUTRAL_PROMPT).strip()[:400],
    }
    files = {"file": (filename, audio, mime)}
    headers = {"Authorization": f"Bearer {settings.stt_api_key}"}

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(url, data=data, files=files, headers=headers)
        if r.status_code != 200:
            log.warning("STT %s: %s", r.status_code, r.text[:200])
            return ""
        text = (r.json().get("text") or "").strip()
        return text
    except Exception as e:
        log.warning("STT xatosi: %r", e)
        return ""
