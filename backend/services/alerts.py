"""Admin ogohlantirishlari (K17.3) — AI ustoz yoki ovoz xizmati to'xtasa admin
Telegram'da darhol biladi, o'quvchilar shikoyat qilguncha kutmaydi.

Har tur (kind) uchun kuniga bir marta yuboriladi — spam bo'lmasin. Bot obyekti
`app.state.bot` dan keladi; bot yo'q bo'lsa (test, preview) jim o'tadi.
"""

import asyncio
import logging
from datetime import datetime, timezone

from config import settings
from services.stats import TASHKENT_OFFSET

log = logging.getLogger(__name__)

KINDS = {
    "credit": (
        "🚨 <b>AI ustoz to'xtadi — Anthropic krediti tugagan.</b>\n"
        "O'quvchilar «Ustoz hozircha band» xabarini ko'rmoqda.\n\n"
        "Yechim: console.anthropic.com → Billing → kredit qo'shish."
    ),
    "auth": (
        "🚨 <b>AI ustoz to'xtadi — ANTHROPIC_API_KEY rad etildi.</b>\n"
        "Kalit noto'g'ri yoki bekor qilingan.\n\n"
        "Yechim: console.anthropic.com → API Keys → yangi kalit → serverda "
        ".env → <code>systemctl restart arabiy</code>."
    ),
    "stt_auth": (
        "🎤 <b>Mikrofon ishlamayapti — STT_API_KEY rad etildi (401).</b>\n"
        "O'quvchilar ovozli javob bera olmayapti.\n\n"
        "Yechim: console.groq.com → API Keys → «gsk_…» kalit → serverda .env "
        "<code>STT_API_KEY=</code> → restart."
    ),
    "stt_down": (
        "🎤 <b>Ovoz xizmati javob bermayapti</b> ({detail}).\n"
        "Vaqtinchalik bo'lishi mumkin — davom etsa, status.groq.com ni tekshiring."
    ),
    "stt_rate": (
        "🎤 <b>Ovoz xizmati limitga urildi (Groq 429).</b>\n"
        "Bepul tarif: 20 so'rov/daqiqa, 2000/kun — ba'zi o'quvchilar «xizmat band» "
        "xabarini ko'rdi, ovozi «tanilmadi».\n\n"
        "Yechim: console.groq.com → Settings → Billing → <b>Dev Tier</b> "
        "(pay-as-you-go, whisper ≈ $0.04/soat audio) — limitlar bir necha barobar oshadi."
    ),
}

# kind → yuborilgan sana (Toshkent, ISO) — kuniga bir marta
_sent_on: dict[str, str] = {}
_sent_at: dict[str, datetime] = {}
_tasks: set[asyncio.Task] = set()


def _today() -> str:
    return (datetime.now(timezone.utc).replace(tzinfo=None) + TASHKENT_OFFSET).date().isoformat()


def last_sent() -> dict[str, datetime]:
    """Hisobot uchun: kind → oxirgi yuborilgan vaqt (naive UTC)."""
    return dict(_sent_at)


def reset() -> None:
    _sent_on.clear()
    _sent_at.clear()


async def notify(bot, kind: str, detail: str = "") -> bool:
    """Adminga xabar; bugun shu tur yuborilgan bo'lsa — False."""
    if bot is None or not settings.admin_id or kind not in KINDS:
        return False
    today = _today()
    if _sent_on.get(kind) == today:
        return False
    _sent_on[kind] = today  # avval belgilaymiz — parallel so'rovlar ikki marta yubormasin
    text = KINDS[kind].format(detail=detail or "—")
    try:
        await bot.send_message(settings.admin_id, text, parse_mode="HTML")
    except Exception as e:
        log.warning("admin ogohlantirish (%s) yuborilmadi: %r", kind, e)
        _sent_on.pop(kind, None)  # keyingi so'rovda qayta uriniladi
        return False
    _sent_at[kind] = datetime.now(timezone.utc).replace(tzinfo=None)
    log.error("ADMIN OGOHLANTIRILDI: %s %s", kind, detail)
    return True


def fire(bot, kind: str, detail: str = "") -> None:
    """Fon vazifasi — o'quvchi javobi Telegram'ni kutib kechikmaydi."""
    if bot is None or not settings.admin_id or kind not in KINDS:
        return
    if _sent_on.get(kind) == _today():
        return
    try:
        task = asyncio.get_running_loop().create_task(notify(bot, kind, detail))
    except RuntimeError:
        return
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
