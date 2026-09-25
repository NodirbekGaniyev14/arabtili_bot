"""Yozuv mashqi eslatmasi (K19.2) — har yangi matn kuni (2 kunda bir) bot xabari.

Kimga: rejasi bor, oxirgi 14 kunda faol (XP olgan), demo emas. Davr uchun bir marta
(`users.writing_notice` = davr kaliti). Kunduzi 10–20 Toshkent. Tugma → Mini App #writing.
`process(session, bot, now)` — halqa/test uchun; `loop` — lifespan'da fon vazifasi.
"""

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from services import notify_prefs
from db.models import Plan, User, XpLog, utcnow
from services import writing
from services.stats import TASHKENT_OFFSET

log = logging.getLogger(__name__)

CHECK_INTERVAL = 1200  # 20 daqiqa
HOUR_FROM, HOUR_TO = 10, 20  # Toshkent
ACTIVE_DAYS = 14
SEND_PAUSE = 0.05

KIND_WORD = {"so'zlar": "so'zlar to'plami", "matn": "qisqa matn", "hikoya": "kichik hikoya",
             "maqol": "maqollar", "she'r": "she'r", "xat": "xat"}


def _local(now: datetime) -> datetime:
    return now + TASHKENT_OFFSET


def _due(now: datetime) -> bool:
    local = _local(now)
    return writing.is_period_start(local.date()) and HOUR_FROM <= local.hour < HOUR_TO


def text_message(name: str, level: str, text: dict) -> str:
    kind = KIND_WORD.get(text["kind"], text["kind"])
    first = text["ar"].split("\n")[0]
    return (
        f"✍️ <b>Yangi yozuv mashqi</b> — {kind} ({level})\n"
        f"«{text['title_uz']}»\n\n"
        f"<i>{first}{'…' if chr(10) in text['ar'] else ''}</i>\n\n"
        f"{name}, matnni qog'ozga chiroyli ko'chiring, suratga oling — AI ustoz harflar, "
        "nuqtalar va hamzalarni tekshirib maslahat beradi. +6–16 XP. Yangi matn — 2 kundan keyin."
    )


def open_kb():
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

    from services.deploy_notify import webapp_url_versioned

    url = webapp_url_versioned()
    if not url.startswith("https://"):
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✍️ Yozuv mashqini ochish", web_app=WebAppInfo(url=url + "#writing"))]]
    )


async def process(session: AsyncSession, bot, now: datetime | None = None) -> dict:
    """Bir aylanish: yangi matn kuni kunduzi faollarga eslatma. {"sent", "failed"}."""
    now = now or utcnow()
    out = {"sent": 0, "failed": 0}
    if not _due(now):
        return out
    period = writing.period_key(_local(now).date())
    active_ids = set(
        (
            await session.execute(
                select(XpLog.user_id).where(XpLog.created_at >= now - timedelta(days=ACTIVE_DAYS)).distinct()
            )
        ).scalars().all()
    )
    if not active_ids:
        return out
    rows = (
        await session.execute(
            select(User, Plan.level)
            .join(Plan, Plan.user_id == User.id)
            .where(User.id.in_(active_ids), User.is_demo == 0, User.tg_id > 0, User.writing_notice != period)
            .order_by(Plan.id.desc())
        )
    ).all()
    kb = open_kb()
    seen: set[int] = set()
    for user, level in rows:
        if user.id in seen:  # bir nechta reja — eng oxirgisi (Plan.id desc) birinchi keladi
            continue
        seen.add(user.id)
        user.writing_notice = period  # yetmasa ham qayta urinmaymiz
        if not notify_prefs.enabled(user, "writing"):
            continue
        text = writing.text_for(level)
        try:
            await bot.send_message(user.tg_id, text_message(user.name or "do'stim", level, text),
                                   parse_mode="HTML", reply_markup=kb)
            out["sent"] += 1
        except Exception as e:
            out["failed"] += 1
            log.info("yozuv eslatmasi yetmadi (%s): %r", user.tg_id, e)
        await session.commit()
        await asyncio.sleep(SEND_PAUSE)
    if settings.admin_id and out["sent"]:
        try:
            await bot.send_message(settings.admin_id, f"✍️ Yozuv mashqi eslatmasi ({period}): {out['sent']} ta yuborildi, {out['failed']} ta yetmadi.")
        except Exception as e:
            log.warning("admin yozuv eslatma xabari yuborilmadi: %r", e)
    return out


async def loop(bot) -> None:
    from db.session import SessionLocal

    while True:
        try:
            if _due(utcnow()):
                async with SessionLocal() as session:
                    await process(session, bot)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("Yozuv eslatmasi xatosi: %r", e)
        await asyncio.sleep(CHECK_INTERVAL)
