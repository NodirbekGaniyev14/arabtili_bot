"""Ovoz → matn (speech-to-text) — OpenAI-mos `/audio/transcriptions` endpoint.

Provayderlar ustuvorlik tartibida (`providers()`):
1. OpenAI gpt-4o-transcribe — `STT_OPENAI_API_KEY` bo'lsa (K21.7): aksentli/tinch nutqda
   aniqroq, ~$0.006/daqiqa; javob `json` + `include[]=logprobs` (ishonch bali shundan).
2. Groq Whisper (`STT_API_KEY`, `verbose_json` segmentlari) — asosiy yoki zaxira.
OpenAI xato bersa (401/429/5xx/tarmoq) shu so'rov Groq'da qayta uriniladi — o'quvchi
sezmaydi; xato `openai_error` da, /ustoz va /tekshir ko'rsatadi. «Tushunilmadi»
(200, bo'sh) zaxiraga o'tkazmaydi — bu natija, xato emas.

Claude audio qabul qilmaydi — shuning uchun alohida STT qatlami. Mikrofondan
kelgan webm/mp4/ogg to'g'ridan-to'g'ri yuboriladi (konvertatsiya yo'q).
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import NamedTuple

import httpx

from config import settings

log = logging.getLogger(__name__)

MAX_AUDIO_BYTES = 8 * 1024 * 1024  # 8 MB ≈ 90 s (klient chegarasi) opus/aac 48 kbps
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
PROMPT_MAX = 600  # Whisper oxirgi ~224 tokenni oladi — muhimi (savol, langar) OXIRIDA turadi

# Whisper jimlik/shovqinda «ko'rgan» mashhur iboralar (YouTube subtitr korpusidan):
# bunday matn o'quvchi gapi emas — bo'sh («tushunilmadi») qaytariladi.
HALLUCINATIONS = (
    "اشتركوا في القناة", "اشترك في القناة", "لا تنسى الاشتراك", "لا تنسوا الاشتراك",
    "ترجمة نانسي قنقر", "شكرا للمشاهدة", "شكراً للمشاهدة", "شكرا على المشاهدة",
    "إلى اللقاء في الحلقة", "الى اللقاء في الحلقة", "موسيقى", "تصفيق", "ضحك",
    "subscribe", "amara.org", "www.",
)
NO_SPEECH_MAX = 0.85  # barcha segmentlarda shundan yuqori → nutq yo'q


def _norm(s: str) -> str:
    s = re.sub(r"[\u064b-\u0652\u0670\u0640]", "", s or "")
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def is_hallucination(text: str, prompt: str = "") -> bool:
    """Whisper matni o'quvchi nutqi emas: mashhur subtitr iboralari, prompt aks-sadosi,
    bitta so'zning takrori, faqat belgi/raqam."""
    t = _norm(text)
    if not t:
        return True
    low = t
    if any(_norm(h) in low for h in HALLUCINATIONS):
        return True
    p = _norm(prompt)
    if p and len(t) >= 12 and t in p:
        return True  # savol/langarni o'zi qaytardi
    words = t.split()
    if len(words) >= 4 and len(set(words)) <= max(1, len(words) // 3):
        return True  # «نعم نعم نعم نعم» kabi sirtmoq
    if not re.search(r"[\u0600-\u06ff]", t):
        return True  # arab harfi yo'q (raqam, lotin, belgi)
    return False


def _no_speech(data: dict) -> bool:
    segs = data.get("segments") or []
    if not segs:
        return False
    return all(float(s.get("no_speech_prob", 0) or 0) > NO_SPEECH_MAX for s in segs)


def build_prompt(context: str = "", words: list[str] | None = None) -> str:
    """Whisper prompt: [mavzu so'zlari] [oxirgi savol] [langar]. Muhimi oxirida —
    model prompt'ning oxirgi ~224 tokenini ko'radi."""
    parts = []
    if words:
        parts.append(" ".join(_norm(w) for w in words if w)[:PROMPT_MAX // 2])
    if context.strip():
        parts.append(context.strip()[:300])
    parts.append(NEUTRAL_PROMPT)
    out = " ".join(p for p in parts if p)
    return out[-PROMPT_MAX:]


# Oxirgi chaqiruv holati (BARCHA provayderlar yiqilganda): "" (ok) | "auth" (401/403 —
# kalit noto'g'ri) | "rate" (429, qayta urinish ham o'tmadi) | "http:<kod>" | "net".
# API shu orqali admin'ni ogohlantiradi (services/alerts.py).
last_error: str = ""
# OpenAI'ning oxirgi xatosi (Groq zaxira ishlagan bo'lsa ham) — /ustoz, /tekshir ko'rsatadi
openai_error: str = ""


class Provider(NamedTuple):
    name: str  # "openai" | "groq"
    key: str
    base_url: str
    model: str


def providers() -> list[Provider]:
    """Ustuvorlik tartibida: OpenAI (kalit bo'lsa) → Groq/asosiy STT."""
    out: list[Provider] = []
    if settings.stt_openai_api_key:
        out.append(Provider("openai", settings.stt_openai_api_key, settings.stt_openai_base_url, settings.stt_openai_model))
    if settings.stt_api_key:
        out.append(Provider("groq", settings.stt_api_key, settings.stt_base_url, settings.stt_model))
    return out


# OpenAI transkripsiya narxi, $/1M token: (audio kirish, matn kirish, chiqish). ≈ $0.006 / daqiqa
OPENAI_PRICE = {
    "gpt-4o-transcribe": (6.0, 2.5, 10.0),
    "gpt-4o-mini-transcribe": (3.0, 1.25, 5.0),
}


def openai_cost(model: str, usage: dict | None) -> float:
    """Javobdagi `usage` dan USD. Token-asosli (gpt-4o-*) yoki davomiylik (whisper-1, $0.006/daq)."""
    if not usage:
        return 0.0
    if usage.get("type") == "duration":
        return float(usage.get("seconds") or 0) / 60 * 0.006
    a, t, o = OPENAI_PRICE.get(model, OPENAI_PRICE["gpt-4o-transcribe"])
    det = usage.get("input_token_details") or {}
    audio = float(det.get("audio_tokens") or 0)
    text = float(det.get("text_tokens") or 0)
    out = float(usage.get("output_tokens") or 0)
    return (audio * a + text * t + out * o) / 1_000_000


# Kunlik hisoblagichlar (xotirada, Toshkent kuni): /ustoz va /tekshir uchun —
# «ba'zi o'quvchilarni tanimayapti» shikoyatida 429/xato ulushi darhol ko'rinadi.
_EMPTY_STATS = {"ok": 0, "empty": 0, "rate": 0, "fail": 0, "retried": 0,
                "openai": 0, "openai_fail": 0, "fallback": 0, "openai_cost": 0.0}
_stats: dict = {"day": "", **_EMPTY_STATS}


def _bump(kind: str, amount: float = 1) -> None:
    from services.stats import TASHKENT_OFFSET

    day = (datetime.now(timezone.utc).replace(tzinfo=None) + TASHKENT_OFFSET).date().isoformat()
    if _stats["day"] != day:
        _stats.update(day=day, **_EMPTY_STATS)
    _stats[kind] = _stats.get(kind, 0) + amount


def stats() -> dict:
    """Bugungi hisob: ok / empty (tushunilmadi) / rate (429) / fail / retried /
    openai (muvaffaqiyat) / openai_fail / fallback (Groq'ga o'tish) / openai_cost (USD)."""
    _bump("ok", 0)  # kunni yangilash; hisobga ta'sir qilmaydi
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
    return bool(providers())


def confidence_from_logprobs(lps: list | None) -> int:
    """gpt-4o-transcribe `logprobs` (token bo'yicha) → 0-100. O'rtacha logprob -0.1 va
    yuqori → 100; -1.0 → 30; oraliq chiziqli. Bo'sh → -1 (o'lchanmagan)."""
    vals = [float(x["logprob"]) for x in (lps or []) if isinstance(x, dict) and x.get("logprob") is not None]
    if not vals:
        return -1
    lp = sum(vals) / len(vals)
    conf = 100 - max(-0.1 - lp, 0.0) / 0.9 * 70
    return int(max(0, min(100, round(conf))))


def confidence_of(data: dict) -> int:
    """Whisper segmentlaridan «aniqlik» bali 0-100 (mock talaffuz mezoni);
    gpt-4o-transcribe javobida segment yo'q — `logprobs` dan (confidence_from_logprobs).

    avg_logprob — model o'z tanishiga qanchalik ishongani: ravon, aniq nutqda
    ≈ -0.1…-0.3, g'o'ldirash/shovqinda -0.8 va past. Davomiylik bo'yicha
    o'rtacha olinadi; segment yo'q bo'lsa (boshqa provayder) -1 = o'lchanmagan."""
    segs = data.get("segments") or []
    if not segs:
        return confidence_from_logprobs(data.get("logprobs")) if data.get("logprobs") else -1
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


def _form(p: Provider, prompt: str, lang: str = "ar") -> dict:
    """So'rov maydonlari provayderga qarab: gpt-4o-* faqat json/text beradi (verbose_json yo'q),
    ishonch uchun `include[]=logprobs`; Whisper — verbose_json segmentlari.
    lang="ar" — ustoz (arab yozuvi langari); boshqa til (masalan "uz", so'rov ovozli fikri) — prompt'siz."""
    data = {"model": p.model, "language": lang}
    if lang == "ar":
        # Prompt: mavzu so'zlari + oxirgi ustoz savoli + arab yozuvi langari (build_prompt)
        data["prompt"] = prompt if prompt.endswith(NEUTRAL_PROMPT) else build_prompt(prompt)
    if p.model.startswith("gpt-4o"):
        data["response_format"] = "json"
        data["include[]"] = "logprobs"
    else:
        data["response_format"] = "verbose_json"
        data["temperature"] = "0"
    return data


def _classify(r: httpx.Response) -> str:
    if r.status_code in (401, 403):
        return "auth"
    if r.status_code == 429:
        return "rate"
    return f"http:{r.status_code}"


async def _post(p: Provider, data: dict, files: dict) -> httpx.Response:
    """Bitta provayderga so'rov; 429 bo'lsa «retry-after» qadar kutib bir marta qayta."""
    url = p.base_url.rstrip("/") + "/audio/transcriptions"
    headers = {"Authorization": f"Bearer {p.key}"}
    async with _SEM, httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.post(url, data=data, files=files, headers=headers)
        if r.status_code == 429:
            wait = min(_retry_after(r), RATE_WAIT_MAX)
            log.info("STT %s 429 — %.1f s kutib qayta urinamiz", p.name, wait)
            _bump("retried")
            await asyncio.sleep(wait)
            r = await client.post(url, data=data, files=files, headers=headers)
    return r


async def transcribe_ex(
    audio: bytes, filename: str = "speech.webm", mime: str = "audio/webm", prompt: str = "", lang: str = "ar"
) -> tuple[str, int]:
    """Audio → (matn, aniqlik bali 0-100 yoki -1). Xatoda ("", -1).
    Provayderlar navbati: OpenAI (bo'lsa) → Groq; birinchisi xato bersa keyingisi.
    lang != "ar" bo'lsa arabcha gallyutsinatsiya filtri qo'llanmaydi (faqat bo'sh matn tashlanadi)."""
    global last_error, openai_error
    ps = providers()
    if not ps:
        return "", -1
    if not audio or len(audio) > MAX_AUDIO_BYTES:
        return "", -1

    files = {"file": (filename, audio, mime)}
    err = ""
    for i, p in enumerate(ps):
        try:
            r = await _post(p, _form(p, prompt, lang), files)
        except Exception as e:
            log.warning("STT %s xatosi: %r", p.name, e)
            r = None
        if r is not None and r.status_code == 200:
            if p.name == "openai":
                openai_error = ""
            last_error = ""
            body = r.json()
            text = (body.get("text") or "").strip()
            if text and (_no_speech(body) or (lang == "ar" and is_hallucination(text, prompt))):
                log.info("STT: nutq emas / gallyutsinatsiya tashlandi: %r", text[:60])
                text = ""
            _bump("ok" if text else "empty")
            if p.name == "openai":
                _bump("openai")
                _bump("openai_cost", openai_cost(p.model, body.get("usage")))
            return text, (confidence_of(body) if text else -1)
        err = _classify(r) if r is not None else "net"
        if r is not None:
            log.warning("STT %s %s: %s", p.name, r.status_code, r.text[:200])
        if p.name == "openai":
            openai_error = err
            _bump("openai_fail")
        if i < len(ps) - 1:
            log.warning("STT %s xato (%s) — %s zaxirasiga o'tamiz", p.name, err, ps[i + 1].name)
            _bump("fallback")
    # Hammasi yiqildi — oxirgi (zaxira) provayder xatosi admin ogohlantirishiga
    last_error = err
    _bump("rate" if err == "rate" else "fail")
    return "", -1


async def transcribe(
    audio: bytes, filename: str = "speech.webm", mime: str = "audio/webm", prompt: str = "", lang: str = "ar"
) -> str:
    """Audio baytlarni matnga aylantiradi (standart — arabcha). Xatoda bo'sh satr."""
    text, _ = await transcribe_ex(audio, filename, mime, prompt, lang)
    return text
