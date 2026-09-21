"""Tizim tekshiruvi (K18.0) — admin `/tekshir`: kalitlar JONLI tekshiriladi.

`/ustoz` faqat «kalit bor/yo'q» deydi; bu yerda Anthropic (1 token), Groq
(`/models`, bepul), edge-tts (qisqa sintez), DB jadvallari, webapp, fon
halqalari, disk — ✅/⚠️/❌ va har ❌ uchun yechim. Noto'g'ri kalitni
birinchi o'quvchi emas, admin topsin.
"""

import asyncio
import logging
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from config import BASE_DIR, settings

log = logging.getLogger(__name__)

# Fon halqalari (main.py lifespan ro'yxatga oladi) — yiqilgan bo'lsa ko'rinadi
_tasks: dict[str, asyncio.Task] = {}

REQUIRED_TABLES = (
    "users", "tutor_turns", "mock_results", "payment_requests", "ai_usage",
    "tutor_mistakes", "drill_results", "daily_speaking", "testimonials", "certificates",
    "listening_results", "tutor_ratings", "writing_results", "trace_results",
)
REQUIRED_COLUMNS = {
    "users": ("vip_until", "paywall_seen_at", "vip_notice", "discount_notified", "trial_until", "speak_report_key", "writing_notice", "winback_stage", "winback_at", "day2_notice"),
    "payment_requests": ("provider", "charge_id", "provider_charge_id"),
    "tutor_turns": ("mode", "score", "vocab", "grammar", "content", "pron"),
    "mock_results": ("vocab", "grammar", "content", "pron"),
}


def register_task(name: str, task: asyncio.Task | None) -> None:
    if task is not None:
        _tasks[name] = task


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _ok(line: str) -> str:
    return f"✅ {_esc(line)}"


def _warn(line: str, fix: str = "") -> str:
    return f"⚠️ {_esc(line)}" + (f"\n    ↳ {_esc(fix)}" if fix else "")


def _bad(line: str, fix: str = "") -> str:
    return f"❌ {_esc(line)}" + (f"\n    ↳ {_esc(fix)}" if fix else "")


async def check_anthropic() -> str:
    key = settings.anthropic_api_key
    if not key:
        return _bad("Anthropic: ANTHROPIC_API_KEY bo'sh", "console.anthropic.com → API Keys → .env → restart")
    if not key.startswith("sk-ant-"):
        return _warn("Anthropic: kalit «sk-ant-» bilan boshlanmaydi — Anthropic kaliti emasga o'xshaydi")
    try:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=key)
        t0 = time.monotonic()
        await asyncio.wait_for(
            client.messages.create(
                model=settings.tutor_model, max_tokens=1, messages=[{"role": "user", "content": "hi"}]
            ),
            timeout=20,
        )
        return _ok(f"Anthropic: {settings.tutor_model} javob berdi ({time.monotonic() - t0:.1f}s)")
    except Exception as e:
        from services.tutor import classify

        kind, _ = classify(e)
        if kind == "credit":
            return _bad("Anthropic: kredit tugagan", "console.anthropic.com → Billing → kredit qo'shish")
        if kind == "auth":
            return _bad("Anthropic: kalit rad etildi (401)", "console.anthropic.com → API Keys → yangi kalit → .env")
        if kind == "rate":
            return _warn("Anthropic: rate limit — hozir band, kalit ishlaydi")
        return _bad(f"Anthropic: {type(e).__name__}: {str(e)[:120]}")


async def check_stt() -> str:
    key = settings.stt_api_key
    if not key:
        return _bad(
            "Ovoz (STT): STT_API_KEY bo'sh — mikrofon o'chiq",
            "console.groq.com → API Keys → «gsk_…» → .env STT_API_KEY → restart",
        )
    is_groq = "groq.com" in settings.stt_base_url
    if is_groq and key.startswith("sk-ant-"):
        return _bad(
            "Ovoz (STT): STT_API_KEY ga Anthropic kaliti qo'yilgan — Groq «gsk_…» kaliti kerak",
            "console.groq.com → API Keys → .env STT_API_KEY=gsk_… → restart",
        )
    if is_groq and not key.startswith("gsk_"):
        return _warn("Ovoz (STT): Groq kaliti odatda «gsk_» bilan boshlanadi — tekshiring")
    url = settings.stt_base_url.rstrip("/") + "/models"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url, headers={"Authorization": f"Bearer {key}"})
    except Exception as e:
        return _bad(f"Ovoz (STT): tarmoq xatosi — {type(e).__name__}", "server internetini / STT_BASE_URL ni tekshiring")
    if r.status_code in (401, 403):
        return _bad("Ovoz (STT): kalit rad etildi (401)", "console.groq.com → yangi kalit → .env → restart")
    if r.status_code != 200:
        return _warn(f"Ovoz (STT): /models {r.status_code} — kalit ishlashi mumkin, tekshirib bo'lmadi")
    try:
        ids = {m.get("id") for m in r.json().get("data", [])}
    except Exception:
        ids = set()
    if ids and settings.stt_model not in ids:
        return _warn(
            f"Ovoz (STT): kalit ishlaydi, lekin «{settings.stt_model}» modeli ro'yxatda yo'q",
            "STT_MODEL=whisper-large-v3-turbo",
        )
    return _ok(f"Ovoz (STT): Groq kaliti ishlaydi · {settings.stt_model}")


async def check_tts() -> str:
    from services import tts

    t0 = time.monotonic()
    try:
        key = await asyncio.wait_for(tts.synthesize("مَرْحَبًا", "A1"), timeout=25)
    except Exception as e:
        return _bad(f"Ovoz (TTS): {type(e).__name__}", "edge-tts internetga chiqolmayapti")
    if not key or not tts.path_for(key).exists():
        return _bad("Ovoz (TTS): sintez bo'lmadi", "edge-tts / internet; journalctl -u arabiy | grep TTS")
    files = list(tts.cache_dir().glob("*.mp3"))
    size_mb = sum(f.stat().st_size for f in files) / 1e6
    return _ok(f"Ovoz (TTS): edge-tts ishlaydi ({time.monotonic() - t0:.1f}s) · kesh {len(files)} fayl, {size_mb:.0f} MB")


async def check_db() -> list[str]:
    from db.session import DB_PATH, engine

    out: list[str] = []
    try:
        async with engine.connect() as conn:
            tables = {
                row[0]
                for row in await conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'")
            }
            missing = [t for t in REQUIRED_TABLES if t not in tables]
            if missing:
                out.append(_bad(f"DB: jadval yo'q — {', '.join(missing)}", "systemctl restart arabiy (create_all)"))
            else:
                out.append(_ok(f"DB: {len(tables)} jadval, kerakli {len(REQUIRED_TABLES)} tasi bor"))
            for table, cols in REQUIRED_COLUMNS.items():
                if table not in tables:
                    continue
                have = {row[1] for row in await conn.exec_driver_sql(f"PRAGMA table_info({table})")}
                lost = [c for c in cols if c not in have]
                if lost:
                    out.append(_bad(f"DB: {table} ustunlari yo'q — {', '.join(lost)}", "restart (migratsiya)"))
            users = (await conn.exec_driver_sql("SELECT COUNT(*) FROM users")).scalar()
    except Exception as e:
        return [_bad(f"DB: {type(e).__name__}: {str(e)[:100]}")]
    try:
        size_mb = Path(DB_PATH).stat().st_size / 1e6
        out.append(_ok(f"DB fayli: {DB_PATH} · {size_mb:.1f} MB · {users} foydalanuvchi"))
    except OSError:
        out.append(_warn(f"DB fayli topilmadi: {DB_PATH}"))
    return out


def check_webapp() -> list[str]:
    from services.deploy_notify import current_version

    out: list[str] = []
    url = settings.webapp_url
    if not url:
        out.append(_bad("Webapp: WEBAPP_URL bo'sh — Mini App tugmalari ishlamaydi", ".env WEBAPP_URL=https://…"))
    elif not url.startswith("https://"):
        out.append(_bad("Webapp: WEBAPP_URL https emas — Telegram faqat https qabul qiladi"))
    else:
        out.append(_ok(f"Webapp: {url}"))
    dist = BASE_DIR / "webapp" / "dist"
    index = dist / "index.html"
    if not index.exists():
        out.append(_bad("Webapp: webapp/dist yo'q — ilova ochilmaydi", "git pull (dist commit qilinadi)"))
    else:
        age_h = (time.time() - index.stat().st_mtime) / 3600
        out.append(_ok(f"Webapp build: dist bor, {age_h:.0f} soat oldin yangilangan"))
    v = current_version()
    out.append(_ok(f"Versiya: {v}") if v else _warn("Versiya: git topilmadi (deploy xabari va ?v= ishlamaydi)"))
    return out


def check_settings() -> list[str]:
    out: list[str] = []
    out.append(_ok(f"Admin: ADMIN_ID={settings.admin_id}") if settings.admin_id else _bad("ADMIN_ID bo'sh — ogohlantirish va cheklar kelmaydi"))
    out.append(_ok("Bot: BOT_TOKEN bor") if settings.bot_token else _bad("BOT_TOKEN bo'sh"))
    digits = "".join(ch for ch in settings.pay_card_number if ch.isdigit())
    if len(digits) >= 16:
        out.append(_ok(f"To'lov: karta …{digits[-4:]} · {settings.pay_card_holder or '— egasi yo’q'}"))
    else:
        out.append(_bad("To'lov: PAY_CARD_NUMBER bo'sh yoki qisqa — paywall'da karta ko'rinmaydi", ".env PAY_CARD_NUMBER / PAY_CARD_HOLDER"))
    out.append(
        _ok(f"Yordam: @{settings.support_username.lstrip('@')}")
        if settings.support_username
        else _warn("SUPPORT_USERNAME bo'sh — paywall'da «admin» deb chiqadi")
    )
    token = settings.pay_provider_token.strip()
    out.append(
        _ok(f"Avto to'lov: {settings.pay_provider_name} · token …{token[-4:]}")
        if token
        # Ataylab o'chiq bo'lishi mumkin (chek oqimi yetarli) — ogohlantirish emas
        else _ok("Avto to'lov: o'chiq — chek oqimi (xohlasangiz .env PAY_PROVIDER_TOKEN)")
    )
    out.append(_ok(f"Limitlar: VIP {settings.tutor_daily_turns}/kun · bepul {settings.tutor_free_turns}/kun · chegirma {settings.pay_discount_hours} soat"))
    return out


def check_tasks() -> list[str]:
    out: list[str] = []
    if not _tasks:
        return [_warn("Fon halqalari ro'yxatga olinmagan (preview rejimi?)")]
    for name, task in _tasks.items():
        if task.done():
            exc = None
            try:
                exc = task.exception()
            except Exception:
                pass
            out.append(_bad(f"Fon halqasi «{name}» to'xtagan{f': {exc!r}' if exc else ''}", "systemctl restart arabiy"))
        else:
            out.append(_ok(f"Fon halqasi «{name}» ishlayapti"))
    return out


def check_disk() -> str:
    from db.session import DB_PATH

    try:
        usage = shutil.disk_usage(Path(DB_PATH).parent)
    except Exception:
        return _warn("Disk: o'lchab bo'lmadi")
    free_gb = usage.free / 1e9
    if free_gb < 1:
        return _bad(f"Disk: {free_gb:.1f} GB bo'sh — TTS kesh/sertifikatlar to'xtaydi", "eski tts/*.mp3 ni tozalang")
    return _ok(f"Disk: {free_gb:.1f} GB bo'sh")


def check_alerts() -> str:
    from services import alerts

    sent = alerts.last_sent()
    if not sent:
        return _ok("Ogohlantirishlar: bugun yuborilmagan")
    return _warn("Ogohlantirishlar bugun: " + ", ".join(f"{k} {v:%H:%M}" for k, v in sent.items()))


async def run_all() -> str:
    """Hamma tekshiruv — HTML hisobot (Telegram)."""
    t0 = time.monotonic()
    anth, stt_line, tts_line, db_lines = await asyncio.gather(
        check_anthropic(), check_stt(), check_tts(), check_db()
    )
    lines = [
        "🩺 <b>Tizim tekshiruvi</b>",
        "",
        "<b>AI va ovoz</b>",
        anth,
        stt_line,
        tts_line,
        "",
        "<b>Ma'lumotlar</b>",
        *db_lines,
        check_disk(),
        "",
        "<b>Ilova va bot</b>",
        *check_webapp(),
        *check_settings(),
        *check_tasks(),
        check_alerts(),
    ]
    bad = sum(1 for line in lines if line.startswith("❌"))
    warn = sum(1 for line in lines if line.startswith("⚠️"))
    now = datetime.now(timezone.utc).strftime("%d.%m %H:%M UTC")
    summary = "🟢 Hammasi joyida" if not bad and not warn else f"{'🔴' if bad else '🟡'} {bad} xato · {warn} ogohlantirish"
    lines += ["", f"{summary} · {time.monotonic() - t0:.1f}s · {now}"]
    return "\n".join(lines)
