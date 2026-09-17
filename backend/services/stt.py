"""Ovoz → matn (speech-to-text) — OpenAI-mos `/audio/transcriptions` endpoint.

Groq (whisper-large-v3-turbo) yoki OpenAI (gpt-4o-mini-transcribe) — ikkalasi
bir xil so'rov formatini qabul qiladi, shuning uchun provayder faqat .env
orqali almashadi (STT_BASE_URL / STT_MODEL / STT_API_KEY).

Claude audio qabul qilmaydi — shuning uchun alohida STT qatlami. Mikrofondan
kelgan webm/mp4/ogg to'g'ridan-to'g'ri yuboriladi (konvertatsiya yo'q).
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone

import httpx

from config import settings

log = logging.getLogger(__name__)

MAX_AUDIO_BYTES = 3 * 1024 * 1024  # 3 MB ≈ 20-25 soniya opus/aac
TIMEOUT = 25.0
# Groq bepul tarifi: whisper-large-v3-turbo 20 so'rov/daqiqa, 2000/kun. 429 kelsa
# «retry-after» qadar (ko'pi bilan RATE_WAIT_MAX s) kutib BIR marta qayta uriniladi —
# 20 RPM oynasi odatda 1-3 soniyada bo'shaydi. Parallel so'rovlar ham cheklanadi.
RATE_WAIT_MAX = 6.0
_SEM = asyncio.Semaphore(8)
_RETRY_IN = re.compile(r"try again in ([\d.]+)\s*(ms|s)", re.I)

# Whisper'ga til/uslub «langar»i: arab yozuvi, fusha. Prompt kontekst beradi,
# lekin mazmunni «taklif qilmaydi» — talaffuz bahosida ham xolis qoladi.
NEUTRAL_PROMPT = "الكلام التالي باللغة العربية."


# Oxirgi chaqiruv holati: "" (ok) | "auth" (401/403 — kalit noto'g'ri) | "rate" (429,
# qayta urinish ham o'tmadi) | "http:<kod>" | "net". API shu orqali admin'ni
# ogohlantiradi (services/alerts.py).
last_error: str = ""

# Kunlik hisoblagichlar (xotirada, Toshkent kuni): /ustoz va /tekshir uchun —
# «ba'zi o'quvchilarni tanimayapti» shikoyatida 429/xato ulushi darhol ko'rinadi.
_stats: dict = {"day": "", "ok": 0, "empty": 0, "rate": 0, "fail": 0, "retried": 0}


def _bump(kind: str) -> None:
    from services.stats import TASHKENT_OFFSET

    day = (datetime.now(timezone.utc).replace(tzinfo=None) + TASHKENT_OFFSET).date().isoformat()
    if _stats["day"] != day:
        _stats.update(day=day, ok=0, empty=0, rate=0, fail=0, retried=0)
    _stats[kind] += 1


def stats() -> dict:
    """Bugungi hisob: ok / empty (tushunilmadi) / rate (429) / fail / retried."""
    _bump("ok")
    _stats["ok"] -= 1  # kunni yangilash uchun; hisobga ta'sir qilmaydi
    return dict(_stats)


def _retry_after(r: httpx.Response) -> float:
    """429 javobidan kutish vaqti (soniya): «retry-after» sarlavhasi yoki matndagi
    «try again in 1.2s»; topilmasa 2 s."""
    hdr = r.headers.get("retry-after", "")
    try:
        if hdr:
            return max(float(hdr), 0.2)
    except ValueError:
        pass
    m = _RETRY_IN.search(r.text or "")
    if m:
        val = float(m.group(1))
        return max(val / 1000 if m.group(2).lower() == "ms" else val, 0.2)
    return 2.0


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
        async with _SEM, httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(url, data=data, files=files, headers=headers)
            if r.status_code == 429:
                wait = min(_retry_after(r), RATE_WAIT_MAX)
                log.info("STT 429 — %.1f s kutib qayta urinamiz", wait)
                _bump("retried")
                await asyncio.sleep(wait)
                r = await client.post(url, data=data, files=files, headers=headers)
        if r.status_code != 200:
            log.warning("STT %s: %s", r.status_code, r.text[:200])
            if r.status_code in (401, 403):
                last_error = "auth"
            elif r.status_code == 429:
                last_error = "rate"
            else:
                last_error = f"http:{r.status_code}"
            _bump("rate" if r.status_code == 429 else "fail")
            return "", -1
        last_error = ""
        body = r.json()
        text = (body.get("text") or "").strip()
        _bump("ok" if text else "empty")
        return text, (confidence_of(body) if text else -1)
    except Exception as e:
        log.warning("STT xatosi: %r", e)
        last_error = "net"
        _bump("fail")
        return "", -1


async def transcribe(
    audio: bytes, filename: str = "speech.webm", mime: str = "audio/webm", prompt: str = ""
) -> str:
    """Audio baytlarni arabcha matnga aylantiradi. Xatoda bo'sh satr."""
    text, _ = await transcribe_ex(audio, filename, mime, prompt)
    return text
