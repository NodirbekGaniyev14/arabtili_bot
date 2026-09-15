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


# Oxirgi chaqiruv holati: "" (ok) | "auth" (401/403 — kalit noto'g'ri) |
# "http:<kod>" | "net". API shu orqali admin'ni ogohlantiradi (services/alerts.py).
last_error: str = ""


def available() -> bool:
    return bool(settings.stt_api_key)


def confidence_of(data: dict) -> int:
    """Whisper segmentlaridan «aniqlik» bali 0-100 (mock talaffuz mezoni).

    avg_logprob — model o'z tanishiga qanchalik ishongani: ravon, aniq nutqda
    ≈ -0.1…-0.3, g'o'ldirash/shovqinda -0.8 va past. Davomiylik bo'yicha
    o'rtacha olinadi; segment yo'q bo'lsa (boshqa provayder) -1 = o'lchanmagan."""
    segs = data.get("segments") or []
    if not segs:
        return -1
    total = 0.0
    weight = 0.0
    no_speech = 0.0
    for s in segs:
        dur = max(float(s.get("end", 0) or 0) - float(s.get("start", 0) or 0), 0.1)
        total += float(s.get("avg_logprob", -1.0) or -1.0) * dur
        weight += dur
        no_speech = max(no_speech, float(s.get("no_speech_prob", 0) or 0))
    lp = total / weight
    # -0.15 va yuqori → 100; -1.2 → 30; oraliq chiziqli
    conf = 100 - max(-0.15 - lp, 0.0) / 1.05 * 70
    if no_speech > 0.5:
        conf -= 20
    return int(max(0, min(100, round(conf))))


async def transcribe_ex(
    audio: bytes, filename: str = "speech.webm", mime: str = "audio/webm", prompt: str = ""
) -> tuple[str, int]:
    """Audio → (arabcha matn, aniqlik bali 0-100 yoki -1). Xatoda ("", -1)."""
    if not available():
        return "", -1
    if not audio or len(audio) > MAX_AUDIO_BYTES:
        return "", -1

    url = settings.stt_base_url.rstrip("/") + "/audio/transcriptions"
    data = {
        "model": settings.stt_model,
        "language": "ar",
        # verbose_json — segmentlar (avg_logprob) ham keladi; matn maydoni bir xil
        "response_format": "verbose_json",
        "temperature": "0",
        # Prompt: mavzu konteksti (oxirgi ustoz savoli) + arab yozuvi langari
        "prompt": (prompt.strip() + " " + NEUTRAL_PROMPT).strip()[:400],
    }
    files = {"file": (filename, audio, mime)}
    headers = {"Authorization": f"Bearer {settings.stt_api_key}"}

    global last_error
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(url, data=data, files=files, headers=headers)
        if r.status_code != 200:
            log.warning("STT %s: %s", r.status_code, r.text[:200])
            last_error = "auth" if r.status_code in (401, 403) else f"http:{r.status_code}"
            return "", -1
        last_error = ""
        body = r.json()
        text = (body.get("text") or "").strip()
        return text, (confidence_of(body) if text else -1)
    except Exception as e:
        log.warning("STT xatosi: %r", e)
        last_error = "net"
        return "", -1


async def transcribe(
    audio: bytes, filename: str = "speech.webm", mime: str = "audio/webm", prompt: str = ""
) -> str:
    """Audio baytlarni arabcha matnga aylantiradi. Xatoda bo'sh satr."""
    text, _ = await transcribe_ex(audio, filename, mime, prompt)
    return text
