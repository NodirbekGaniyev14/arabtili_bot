"""K30 — jonli ovozli suhbat: o'quvchi ↔ bizning server ↔ Google Gemini Live API (native audio).

Nega relay (brauzer → server → Gemini), to'g'ridan-to'g'ri emas:
  - API kaliti serverda qoladi;
  - davomiylik va sarf shu yerda o'lchanadi (`live_sessions`); limit kerak bo'lsa shu yerda (`allowance`);
  - suhbat matni (transkripsiya) keyin Claude tahliliga beriladi: xatolar daftari, yangi so'zlar, XP.

Audio: kirish 16 kHz PCM16 mono (brauzer AudioWorklet), chiqish 24 kHz PCM16 (Gemini).

Mijoz protokoli (WebSocket /api/v2/live/ws, api/live.py):
  → {"type": "start", "init_data": ..., "topic_id": ...}   birinchi xabar
  → binary                                                  PCM16 16 kHz bo'laklari
  → {"type": "end"}
  ← {"type": "ready", "max_seconds": N}
  ← {"type": "audio", "data": <base64 PCM16 24 kHz>}
  ← {"type": "in", "text": ...}       o'quvchi gapi (transkripsiya bo'lagi)
  ← {"type": "out", "text": ...}      ustoz gapi (transkripsiya bo'lagi)
  ← {"type": "turn"} | {"type": "interrupted"}
  ← {"type": "error", "code": ..., "detail": ...}
  ← {"type": "end", "reason": ..., "seconds": N, "session_id": id}
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import math
import struct
import time
from dataclasses import dataclass, field
from datetime import timedelta

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.models import LiveSession, TutorMistake, User, XpLog, utcnow

log = logging.getLogger(__name__)

IN_RATE = 16_000  # o'quvchi ovozi (Gemini kirishi)
OUT_RATE = 24_000  # ustoz ovozi (Gemini chiqishi)
TOKENS_PER_SECOND = 25  # Gemini audio: 1 soniya = 25 token (ai.google.dev/gemini-api/docs/pricing)
# USD / 1M token — gemini-3.8-live (2026-10-01 narxlari): audio kirish $3, audio chiqish $12, matn $0.75 / $4.50
PRICE_PER_M = {"audio_in": 3.00, "audio_out": 12.00, "text_in": 0.75, "text_out": 4.50}
USAGE_KEYS = tuple(PRICE_PER_M)
TRANSCRIPT_MAX_CHARS = 20_000
LIVE_XP_DAILY_CAP = 60
# Suiiste'molga qarshi: bitta bo'lak ≤ 1 s, umumiy oqim real vaqtdan 1.5× tez bo'lmasin (+2 s zaxira) — skript bilan
# tez-tez ovoz yuborib sarfni oshirib bo'lmaydi (Gemini kirish audiosining har soniyasi pullik)
MAX_FRAME_BYTES = IN_RATE * 2
RATE_SLACK = 1.5
RATE_BURST_SECONDS = 2.0
START_TEXT = "[START] Greet me and begin the conversation."


def api_key() -> str:
    """`.env` dagi kalit — qo'shtirnoq/probel/\\r bilan nusxalangan bo'lsa ham toza (Google bunday kalitni rad etadi)."""
    return (settings.gemini_api_key or "").strip().strip("\"'").strip()


def available() -> bool:
    """«🎙 Jonli AI bilan suhbat» tugmasi ko'rinadimi: kalit bor (yoki preview'da soxta suhbatdosh)."""
    return bool(api_key()) or settings.live_fake


AUTH_MARKERS = ("api key", "api_key", "401", "403", "permission", "authentication", "credential", "unauthenticated")
# «Your project has been denied access» — bepul (billing'siz) loyihaga Live yopiq (Google forum, 2026-09)
PROJECT_MARKERS = ("denied access", "billing", "free tier", "resource_exhausted", "quota", "429")


def is_auth_error(text: str) -> bool:
    low = text.lower()
    return any(m in low for m in AUTH_MARKERS)


def classify_error(text: str) -> str:
    """Gemini xatosi → auth (kalit) | project (billing/ruxsat) | model | down (tarmoq/boshqa)."""
    low = text.lower()
    if any(m in low for m in PROJECT_MARKERS):
        return "project"
    if "not found" in low or "is not supported" in low:
        return "model"
    return "auth" if is_auth_error(low) else "down"


API_ROOT = "https://generativelanguage.googleapis.com/v1beta"


def _google_error(r) -> tuple[str, str]:
    """Google REST xatosi → (matn, sabab kodi: ErrorInfo.reason yoki status, masalan ACCESS_TOKEN_TYPE_UNSUPPORTED)."""
    try:
        err = r.json().get("error", {}) or {}
    except Exception:  # noqa: BLE001
        return r.text[:200], ""
    reason = next((d["reason"] for d in err.get("details") or [] if isinstance(d, dict) and d.get("reason")), "")
    msg = (err.get("message") or "").split(" See https://")[0]  # Google havolasi /tekshir qatorini cho'zadi
    return msg[:200], reason or (err.get("status") or "")


async def probe_key() -> dict:
    """Kalitni REST bilan tekshiradi (WebSocket'dan aniqroq xato beradi) va modellarni topadi.
    Qaytaradi: {"ok", "status", "error", "reason", "live_models": [bidiGenerateContent], "gen_models": [generateContent]}."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{API_ROOT}/models", params={"pageSize": 1000}, headers={"x-goog-api-key": api_key()})
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "status": 0, "error": f"tarmoq: {type(e).__name__}", "reason": "",
                "live_models": [], "gen_models": []}
    if r.status_code != 200:
        msg, reason = _google_error(r)
        return {"ok": False, "status": r.status_code, "error": msg, "reason": reason, "live_models": [], "gen_models": []}
    models = r.json().get("models", [])

    def having(method: str) -> list[str]:
        return sorted(
            m.get("name", "").removeprefix("models/")
            for m in models
            if method in (m.get("supportedGenerationMethods") or [])
        )

    return {"ok": True, "status": 200, "error": "", "reason": "", "live_models": having("bidiGenerateContent"),
            "gen_models": having("generateContent")}


# Kalit bilan HAQIQIY javob olishni tekshirish uchun arzon matn modeli (ro'yxatda bo'lganining birinchisi)
TEXT_MODEL_PREFS = ("gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.1-flash-lite")


def pick_text_model(gen_models: list[str]) -> str:
    for m in TEXT_MODEL_PREFS:
        if m in gen_models:
            return m
    plain = [m for m in gen_models if "flash" in m and not any(x in m for x in ("tts", "live", "image", "audio", "embed"))]
    return plain[0] if plain else ""


async def probe_generate(model: str) -> dict:
    """Bir necha tokenlik so'rov (sarf ~0): kalit ro'yxatni ko'rsa-yu, javob olishda rad etilsa — billing/loyiha muammosi."""
    import httpx

    body = {"contents": [{"parts": [{"text": "ping"}]}], "generationConfig": {"maxOutputTokens": 8}}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(f"{API_ROOT}/models/{model}:generateContent", json=body,
                                  headers={"x-goog-api-key": api_key()})
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "status": 0, "error": f"tarmoq: {type(e).__name__}", "reason": ""}
    if r.status_code != 200:
        msg, reason = _google_error(r)
        return {"ok": False, "status": r.status_code, "error": msg, "reason": reason}
    return {"ok": True, "status": 200, "error": "", "reason": ""}


# ────────────────────────── Prompt ──────────────────────────

VOICE_LEVELS = {
    "A0": "Absolute beginner. Use single words and very short phrases (max 4 Arabic words per turn). "
    "Say the Uzbek translation right after every Arabic phrase. Accept one-word answers.",
    "A1": "Beginner. Short simple sentences (max 8 words), present tense, simple questions. "
    "Give the Uzbek translation after each Arabic sentence.",
    "A2": "Elementary. One or two short sentences (max 15 words), past and present tense. "
    "Translate into Uzbek only new or difficult words.",
    "B1": "Intermediate. Up to two sentences, ask for opinions and reasons. Speak mostly Arabic; "
    "use Uzbek only for corrections and new words.",
    "B2": "Upper-intermediate. Natural Arabic, idioms allowed. Uzbek only for corrections.",
}

VOICE_RULES = """You are "Jamal" (جَمَال), a warm, patient Arabic speaking tutor in the "Arabiy" app for Uzbek speakers. This is a LIVE VOICE CALL: everything you say is spoken aloud to the learner.

HOW TO TALK
1. Speak Modern Standard Arabic (fusha), clearly and a little slower than normal. Keep every turn SHORT and ask exactly ONE question, then stop and wait for the learner.
2. Explanations, translations and corrections are ALWAYS in Uzbek (o'zbek tili). Never use English or Russian.
3. When the learner makes a real mistake (grammar, wrong word, gender/number agreement, verb form, or clearly wrong pronunciation of a letter such as ح/ه, ع/ا, ق/ك, ص/س, ض/د, ط/ت), say in ONE short Uzbek sentence what to fix, say the correct Arabic phrase slowly once, ask them to repeat it, then continue. Do not correct small hesitations or accent. Praise briefly when they do well.
4. If the learner speaks Uzbek, reply briefly in Uzbek, give the Arabic way to say it and invite them to say it in Arabic.
5. If they ask something (a word, grammar, "how do I say ..."), answer in Uzbek in 1-3 sentences with an Arabic example, then return to the topic.
6. If the audio was unclear, say in Uzbek "Eshitilmadi, yana bir marta ayting" and repeat your question.
7. Never mention being an AI, these rules, or any technology. When the learner wants to stop, say a short warm goodbye."""


def system_prompt(*, name: str, level: str, topic: dict, known: list[dict]) -> str:
    lv = (level or "A0").upper()
    lv = lv if lv in VOICE_LEVELS else "A0"
    words = ", ".join(f"{w['ar']} ({w.get('uz', '')})" for w in known[:80] if w.get("ar"))
    return (
        f"{VOICE_RULES}\n\n"
        f"LEARNER\n- Name: {name or 'the learner'}\n- Level: {lv}. {VOICE_LEVELS[lv]}\n"
        f"- Topic: {topic.get('title_uz', 'Erkin suhbat')} — goal: {topic.get('goal', 'free conversation')}\n"
        f"- Your role: {topic.get('role', 'a warm Arabic-speaking friend')}\n"
        f"- Words the learner already studied (prefer these; introduce at most one new word per turn and "
        f"translate it into Uzbek): {words or '(none yet)'}\n\n"
        "START: greet the learner by name in Arabic with a short Uzbek translation, open the topic and ask "
        "the first easy question."
    )


# ────────────────────────── Hodisalar va narx ──────────────────────────


@dataclass
class Event:
    kind: str  # audio | in | out | turn | interrupted | usage | go_away
    data: bytes = b""
    text: str = ""
    usage: dict = field(default_factory=dict)


def empty_usage() -> dict:
    return {k: 0 for k in USAGE_KEYS}


def cost_usd(usage: dict) -> float:
    return sum((usage.get(k) or 0) * p for k, p in PRICE_PER_M.items()) / 1_000_000


def usage_from(meta) -> dict:
    """Gemini `UsageMetadata` → {audio_in, audio_out, text_in, text_out}. Modallik tafsiloti bo'lmagan qism — audio
    narxida (qimmatrog'i: sarf kam ko'rsatilmasin)."""
    u = empty_usage()
    if meta is None:
        return u
    for attr, side in (("prompt_tokens_details", "in"), ("response_tokens_details", "out")):
        details = getattr(meta, attr, None) or []
        counted = 0
        for d in details:
            n = int(getattr(d, "token_count", 0) or 0)
            modality = str(getattr(getattr(d, "modality", None), "value", getattr(d, "modality", "")) or "").upper()
            u[("audio_" if "AUDIO" in modality else "text_") + side] += n
            counted += n
        total = int(getattr(meta, "prompt_token_count" if side == "in" else "response_token_count", 0) or 0)
        if total > counted:
            u["audio_" + side] += total - counted
    return u


def estimate_usage(in_seconds: float, out_seconds: float) -> dict:
    """Gemini usage yubormasa — davomiylikdan taxmin (audio kirish/chiqish 25 token/s)."""
    u = empty_usage()
    u["audio_in"] = int(in_seconds * TOKENS_PER_SECOND)
    u["audio_out"] = int(out_seconds * TOKENS_PER_SECOND)
    return u


def _events_from(msg) -> list[Event]:
    """SDK `LiveServerMessage` → bizning hodisalar."""
    out: list[Event] = []
    sc = getattr(msg, "server_content", None)
    if sc is not None:
        turn = getattr(sc, "model_turn", None)
        for part in (getattr(turn, "parts", None) or []) if turn else []:
            blob = getattr(part, "inline_data", None)
            if blob is not None and getattr(blob, "data", None):
                out.append(Event("audio", data=blob.data))
        it = getattr(sc, "input_transcription", None)
        if it is not None and getattr(it, "text", None):
            out.append(Event("in", text=it.text))
        ot = getattr(sc, "output_transcription", None)
        if ot is not None and getattr(ot, "text", None):
            out.append(Event("out", text=ot.text))
        if getattr(sc, "interrupted", None):
            out.append(Event("interrupted"))
        if getattr(sc, "turn_complete", None):
            out.append(Event("turn"))
    if getattr(msg, "usage_metadata", None) is not None:
        out.append(Event("usage", usage=usage_from(msg.usage_metadata)))
    if getattr(msg, "go_away", None) is not None:
        out.append(Event("go_away"))
    return out


# ────────────────────────── Gemini va soxta suhbatdosh ──────────────────────────


class LiveUnavailable(Exception):
    """Gemini'ga ulanib bo'lmadi. `kind`: auth | down."""

    def __init__(self, message_uz: str, kind: str = "down"):
        super().__init__(message_uz)
        self.message_uz = message_uz
        self.kind = kind


# Ulanish usullari: "key" — kalit sarlavhada (x-goog-api-key); "token" — kalit bilan REST'da vaqtinchalik (ephemeral)
# token olinadi, WebSocket'ga token bilan ulaniladi. Yangi «AQ.» kalitlarni ba'zi akkauntlarda WebSocket rad etadi
# («Expected OAuth 2 access token», Google forum 2026-07…09) — token yo'li shuni chetlab o'tadi.
AUTH_MODES = ("key", "token")
AUTH_MODE = {"mode": "key"}  # oxirgi ishlagan usul (jarayon davomida eslab qolinadi)
CONNECT_TIMEOUT = 15


async def _client(mode: str):
    import warnings
    from datetime import datetime, timezone

    from google import genai

    if mode == "key":
        return genai.Client(api_key=api_key())
    with warnings.catch_warnings():  # SDK: «ephemeral token — experimental»
        warnings.simplefilter("ignore")
        base = genai.Client(api_key=api_key(), http_options={"api_version": "v1alpha"})
        now = datetime.now(timezone.utc)
        token = await asyncio.wait_for(
            base.aio.auth_tokens.create(
                config={
                    "uses": 1,
                    "expire_time": now + timedelta(minutes=30),
                    "new_session_expire_time": now + timedelta(minutes=2),
                }
            ),
            timeout=CONNECT_TIMEOUT,
        )
    return genai.Client(api_key=token.name, http_options={"api_version": "v1alpha"})


async def open_session(mode: str, config: dict):
    """(connect konteksti, sessiya) — xato bo'lsa istisno (chaqiruvchi tasniflaydi)."""
    import warnings

    client = await _client(mode)
    cm = client.aio.live.connect(model=settings.live_model, config=config)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        session = await asyncio.wait_for(cm.__aenter__(), timeout=CONNECT_TIMEOUT)
    return cm, session


async def try_connect(mode: str) -> str:
    """/tekshir: shu usul bilan ulanib, darhol yopadi. Bo'sh satr — ishladi, aks holda xato matni."""
    try:
        cm, _session = await open_session(mode, GeminiLive("You are a test. Do not speak.").config())
    except Exception as e:  # noqa: BLE001
        return (repr(e) or type(e).__name__)[:300]
    try:
        await cm.__aexit__(None, None, None)
    except Exception:  # noqa: BLE001
        pass
    return ""


class GeminiLive:
    """google-genai SDK ustidan yupqa qatlam (SDK JSON maydonlarini o'zi to'g'ri joylaydi)."""

    def __init__(self, system: str):
        self.system = system
        self._cm = None
        self._session = None
        self.mode = ""

    def config(self) -> dict:
        return {
            "response_modalities": ["AUDIO"],
            "system_instruction": self.system,
            "speech_config": {"voice_config": {"prebuilt_voice_config": {"voice_name": settings.live_voice}}},
            "input_audio_transcription": {},
            "output_audio_transcription": {},
            # O'quvchi chet tilida o'ylab gapiradi — pauzada gapini bo'lib yubormaslik uchun sezgirlik past
            "realtime_input_config": {
                "automatic_activity_detection": {
                    "end_of_speech_sensitivity": "END_SENSITIVITY_LOW",
                    "silence_duration_ms": 900,
                    "prefix_padding_ms": 200,
                }
            },
            "context_window_compression": {"sliding_window": {}},
        }

    async def __aenter__(self) -> "GeminiLive":
        # Avval oxirgi ishlagan usul; kalit rad etilsa — ikkinchisi (to'g'ridan-to'g'ri kalit ↔ vaqtinchalik token)
        first = AUTH_MODE["mode"]
        last: Exception | None = None
        for mode in (first, *(m for m in AUTH_MODES if m != first)):
            try:
                self._cm, self._session = await open_session(mode, self.config())
            except Exception as e:  # noqa: BLE001
                last = e
                kind = classify_error(repr(e))
                log.warning("Gemini Live ulanmadi (%s, %s): %s", mode, kind, repr(e)[:300])
                if kind != "auth":
                    break  # kalit muammosi emas — boshqa usul yordam bermaydi
                continue
            AUTH_MODE["mode"] = mode
            self.mode = mode
            return self
        kind = "auth" if classify_error(repr(last)) in ("auth", "project") else "down"
        raise LiveUnavailable("Jonli suhbat hozircha ishlamayapti. Birozdan keyin qayta urinib ko'ring.", kind) from last

    async def __aexit__(self, *exc) -> None:
        if self._cm is not None:
            try:
                await self._cm.__aexit__(None, None, None)
            except Exception as e:  # noqa: BLE001
                log.debug("Gemini Live yopilishi: %r", e)

    async def send_audio(self, pcm: bytes) -> None:
        from google.genai import types

        await self._session.send_realtime_input(audio=types.Blob(data=pcm, mime_type=f"audio/pcm;rate={IN_RATE}"))

    async def send_text(self, text: str) -> None:
        await self._session.send_client_content(turns={"role": "user", "parts": [{"text": text}]}, turn_complete=True)

    async def events(self):
        while True:  # SDK receive() bitta navbat tugaguncha beradi — keyingisi uchun qayta chaqiriladi
            async for msg in self._session.receive():
                for ev in _events_from(msg):
                    yield ev


def tone(seconds: float, freq: float = 440.0, rate: int = OUT_RATE) -> bytes:
    n = int(seconds * rate)
    return b"".join(
        struct.pack("<h", int(6000 * math.sin(2 * math.pi * freq * i / rate) * min(1, i / 800, (n - i) / 800)))
        for i in range(n)
    )


class FakeLive:
    """Kalitsiz sinov (LIVE_FAKE=1, testlar): har ~1.2 s eshitilgan ovozdan keyin qisqa «javob» — signal + matn."""

    HEARD_BYTES = int(IN_RATE * 2 * 1.2)

    def __init__(self, system: str):
        self.system = system
        self.q: asyncio.Queue[Event | None] = asyncio.Queue()
        self.heard = 0
        self.received: list[bytes] = []
        self.texts: list[str] = []

    async def __aenter__(self) -> "FakeLive":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.q.put(None)

    async def _reply(self, ar: str) -> None:
        pcm = tone(0.6)
        for i in range(0, len(pcm), 9600):
            await self.q.put(Event("audio", data=pcm[i : i + 9600]))
        await self.q.put(Event("out", text=ar))
        await self.q.put(Event("usage", usage={**empty_usage(), "audio_in": 30, "audio_out": 15, "text_in": 400}))
        await self.q.put(Event("turn"))

    async def send_text(self, text: str) -> None:
        self.texts.append(text)
        await self._reply("مَرْحَبًا! أَنَا جَمَال. كَيْفَ حَالُكَ؟ (Salom! Men Jamol. Ahvolingiz qanday?)")

    async def send_audio(self, pcm: bytes) -> None:
        self.received.append(pcm)
        self.heard += len(pcm)
        if self.heard >= self.HEARD_BYTES:
            self.heard = 0
            await self.q.put(Event("in", text="أَنَا بِخَيْرٍ"))
            await self._reply("أَحْسَنْتَ! مَا اسْمُكَ؟ (Barakalla! Ismingiz nima?)")

    async def events(self):
        while True:
            ev = await self.q.get()
            if ev is None:
                return
            yield ev


def open_live(system: str):
    """Sessiya yaratuvchi — testlar almashtiradi."""
    return FakeLive(system) if settings.live_fake or not api_key() else GeminiLive(system)


# ────────────────────────── Relay ──────────────────────────


@dataclass
class RelayResult:
    reason: str = ""
    seconds: float = 0.0
    in_bytes: int = 0
    dropped_bytes: int = 0  # juda katta yoki real vaqtdan tez kelgan ovoz (yuborilmadi)
    out_bytes: int = 0
    user_turns: int = 0
    transcript: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=empty_usage)
    usage_reported: bool = False
    error: str = ""

    def final_usage(self) -> dict:
        if self.usage_reported:
            return dict(self.usage)
        return estimate_usage(self.in_bytes / (IN_RATE * 2), self.out_bytes / (OUT_RATE * 2))


async def relay(client, live, *, max_seconds: float, idle_seconds: float, tick: float = 0.5, clock=time.monotonic) -> RelayResult:
    """O'quvchi ↔ Gemini oqimi. `client.recv()` → ("audio", bytes) | ("end", None) | ("disconnect", None) | ("noop", None);
    `client.send(dict)`. Tugash: o'quvchi «end»/uzildi, vaqt tugadi, jimlik, Gemini yopdi yoki xato."""
    res = RelayResult()
    start = clock()
    last_activity = start
    pending = {"user": "", "model": ""}

    def flush(role: str) -> None:
        text = pending[role].strip()
        pending[role] = ""
        if not text:
            return
        res.transcript.append({"role": role, "text": text})
        if role == "user":
            res.user_turns += 1

    async def up() -> None:
        while True:
            kind, data = await client.recv()
            if kind == "audio" and data:
                allowed = (clock() - start + RATE_BURST_SECONDS) * IN_RATE * 2 * RATE_SLACK
                if len(data) > MAX_FRAME_BYTES or res.in_bytes + len(data) > allowed:
                    res.dropped_bytes += len(data)
                    continue
                res.in_bytes += len(data)
                await live.send_audio(data)
            elif kind in ("end", "disconnect"):
                res.reason = res.reason or ("user" if kind == "end" else "disconnect")
                return

    async def down() -> None:
        nonlocal last_activity
        async for ev in live.events():
            now = clock()
            if ev.kind == "audio":
                flush("user")
                res.out_bytes += len(ev.data)
                last_activity = now
                await client.send({"type": "audio", "data": base64.b64encode(ev.data).decode()})
            elif ev.kind == "in":
                flush("model")
                pending["user"] += ev.text
                last_activity = now
                await client.send({"type": "in", "text": ev.text})
            elif ev.kind == "out":
                flush("user")
                pending["model"] += ev.text
                await client.send({"type": "out", "text": ev.text})
            elif ev.kind == "interrupted":
                flush("model")
                await client.send({"type": "interrupted"})
            elif ev.kind == "turn":
                flush("user")
                flush("model")
                last_activity = now
                await client.send({"type": "turn"})
            elif ev.kind == "usage":
                res.usage_reported = True
                for k in USAGE_KEYS:
                    res.usage[k] += ev.usage.get(k, 0)
            elif ev.kind == "go_away":
                res.reason = res.reason or "time"
                return
        res.reason = res.reason or "closed"

    await live.send_text(START_TEXT)
    tasks = {asyncio.create_task(up()), asyncio.create_task(down())}
    try:
        while True:
            done, _ = await asyncio.wait(tasks, timeout=tick, return_when=asyncio.FIRST_COMPLETED)
            for t in done:
                exc = t.exception()
                if exc is not None:
                    res.reason = res.reason or "error"
                    res.error = repr(exc)[:300]
            if done:
                break
            now = clock()
            if now - start >= max_seconds:
                res.reason = "time"
                break
            if now - last_activity >= idle_seconds:
                res.reason = "idle"
                break
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        flush("user")
        flush("model")
        res.seconds = clock() - start
    return res


# ────────────────────────── Limit va sarf ──────────────────────────


def _day_start():
    from services.xp_guard import day_start_utc

    return day_start_utc()


async def seconds_used(session: AsyncSession, user_id: int, since) -> int:
    n = (
        await session.execute(
            select(func.coalesce(func.sum(LiveSession.seconds), 0)).where(
                LiveSession.user_id == user_id, LiveSession.created_at >= since
            )
        )
    ).scalar_one()
    return int(n or 0)


async def allowance(session: AsyncSession, user: User) -> int | None:
    """Qolgan soniyalar; None — cheklovsiz (standart: LIVE_FREE_SECONDS_DAY=0, LIVE_VIP_SECONDS_MONTH=0)."""
    from services import billing

    if billing.is_vip(user):
        cap = settings.live_vip_seconds_month
        since = utcnow() - timedelta(days=30)
    else:
        cap = settings.live_free_seconds_day
        since = _day_start()
    if cap <= 0:
        return None
    return max(0, cap - await seconds_used(session, user.id, since))


async def spent_today(session: AsyncSession) -> float:
    rows = (
        await session.execute(select(func.coalesce(func.sum(LiveSession.cost_usd), 0.0)).where(LiveSession.created_at >= _day_start()))
    ).scalar_one()
    return float(rows or 0.0)


async def save(session: AsyncSession, user: User, topic: str, level: str, res: RelayResult) -> LiveSession:
    usage = res.final_usage()
    text = json.dumps(res.transcript, ensure_ascii=False)
    while len(text) > TRANSCRIPT_MAX_CHARS and res.transcript:
        res.transcript = res.transcript[1:]
        text = json.dumps(res.transcript, ensure_ascii=False)
    row = LiveSession(
        user_id=user.id,
        topic=topic[:24],
        level=level[:4],
        model=("fake" if settings.live_fake or not api_key() else settings.live_model)[:40],
        seconds=int(round(res.seconds)),
        user_turns=res.user_turns,
        audio_in_tokens=usage["audio_in"],
        audio_out_tokens=usage["audio_out"],
        text_in_tokens=usage["text_in"],
        text_out_tokens=usage["text_out"],
        cost_usd=round(cost_usd(usage), 6),
        reason=(res.reason or "closed")[:12],
        transcript=text,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def report(session: AsyncSession) -> dict:
    """Admin `/ustoz` uchun: bugun va 7 kun — suhbatlar, daqiqa, $, foydalanuvchilar."""
    out = {}
    for key, since in (("today", _day_start()), ("week", utcnow() - timedelta(days=7))):
        n, secs, cost, users = (
            await session.execute(
                select(
                    func.count(LiveSession.id),
                    func.coalesce(func.sum(LiveSession.seconds), 0),
                    func.coalesce(func.sum(LiveSession.cost_usd), 0.0),
                    func.count(func.distinct(LiveSession.user_id)),
                ).where(LiveSession.created_at >= since)
            )
        ).one()
        out[key] = {"sessions": int(n or 0), "minutes": round((secs or 0) / 60, 1), "cost": float(cost or 0), "users": int(users or 0)}
    return out


# ────────────────────────── Suhbatdan keyingi tahlil (Claude) ──────────────────────────


class LiveMistake(BaseModel):
    said: str = Field(description="What the learner said (Arabic as in the transcript, may lack harakat)")
    fixed_ar: str = Field(description="Corrected Arabic sentence with full harakat")
    note_uz: str = Field(description="ONE short Uzbek sentence naming the error")


class LiveWord(BaseModel):
    ar: str = Field(description="Arabic word with full harakat")
    translit: str = Field(description="Uzbek-friendly Latin transliteration")
    uz: str = Field(description="Uzbek meaning")


class LiveReview(BaseModel):
    summary_uz: str = Field(description="2-3 warm Uzbek sentences: what went well and the ONE main thing to practise")
    mistakes: list[LiveMistake] = Field(default_factory=list, description="Up to 5 real mistakes of the learner")
    words: list[LiveWord] = Field(default_factory=list, description="Up to 6 useful words from the conversation")


REVIEW_RULES = """You review a LIVE VOICE conversation between an Uzbek learner of Arabic and the tutor Jamal.
The transcript comes from speech recognition: ignore missing harakat, spelling of the recognition and tiny slips.
Return:
- `summary_uz`: 2-3 warm, concrete Uzbek sentences (what went well, the ONE main thing to practise next).
- `mistakes`: up to 5 REAL learner mistakes (grammar, wrong word, agreement, verb form). Skip anything the tutor already accepted as fine. `fixed_ar` with full harakat, `note_uz` one short Uzbek sentence.
- `words`: up to 6 useful words that appeared (prefer ones the learner struggled with), with full harakat, translit and Uzbek meaning.
Never invent content that is not in the transcript."""


def _transcript_text(transcript: list[dict]) -> str:
    return "\n".join(f"{'LEARNER' if t['role'] == 'user' else 'TUTOR'}: {t['text']}" for t in transcript)


async def review(session: AsyncSession, row: LiveSession, user: User) -> dict:
    """Bir marta hisoblanadi (natija `live_sessions.review` da), XP ham bir marta."""
    if row.review:
        try:
            return json.loads(row.review)
        except Exception:  # noqa: BLE001
            pass
    from services import ai_usage, tutor, xp_guard

    transcript = json.loads(row.transcript or "[]")
    result = {"summary_uz": "", "mistakes": [], "words": [], "xp": 0, "seconds": row.seconds, "user_turns": row.user_turns}
    if row.user_turns < 2 or not settings.anthropic_api_key:
        result["summary_uz"] = (
            "Suhbat juda qisqa bo'ldi — keyingi safar kamida 3–4 marta javob bering, shunda tahlil chiqadi."
            if row.user_turns < 2
            else "Tahlil hozircha mavjud emas."
        )
    else:
        tutor._JSON_KEYS.setdefault(LiveReview, "summary_uz, mistakes (list of {said, fixed_ar, note_uz}), words (list of {ar, translit, uz})")
        try:
            out, usage = await tutor._call(
                [{"type": "text", "text": REVIEW_RULES}],
                [{"role": "user", "content": _transcript_text(transcript)[-12_000:]}],
                LiveReview,
                settings.tutor_model,
                max_tokens=1200,
            )
            ai_usage.record(session, "live_review", usage, user.id)
            result["summary_uz"] = out.summary_uz
            result["mistakes"] = [m.model_dump() for m in out.mistakes[:5]]
            result["words"] = [w.model_dump() for w in out.words[:6]]
            for m in result["mistakes"]:
                session.add(
                    TutorMistake(
                        user_id=user.id, kind="live", topic=row.topic, said_ar=m["said"][:400], fixed_ar=m["fixed_ar"][:400], note_uz=m["note_uz"][:400]
                    )
                )
        except tutor.TutorUnavailable as e:
            log.warning("Jonli suhbat tahlili chiqmadi (%s): %s", e.kind, e.message_uz)
            result["summary_uz"] = "Tahlil hozircha tayyorlanmadi — suhbat saqlandi, matnini pastda ko'rasiz."
    if row.user_turns >= 3:
        xp = min(30, 2 * row.user_turns + row.seconds // 60)
        xp = await xp_guard.capped(session, user.id, "live:", xp, LIVE_XP_DAILY_CAP)
        if xp > 0:
            session.add(XpLog(user_id=user.id, amount=xp, source=f"live:{row.id}"))
            result["xp"] = xp
    row.reviewed = 1
    row.review = json.dumps(result, ensure_ascii=False)
    await session.commit()
    return result
