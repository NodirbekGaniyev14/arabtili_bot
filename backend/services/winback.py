"""Qaytarish ketma-ketligi (K20.1) — 3 / 7 / 30 kun kirmaganlarga shaxsiy xabar.

Faollik = oxirgi XP (xp_log); XP'siz foydalanuvchida — reja tuzilgan sana.
Bosqichlar: 3 kun (kartalar va keyingi dars), 7 kun (yangi bo'limlar: yozuv, tinglash,
AI ustoz), 30 kun (hammasi saqlangan, 1 dars yetadi; sinov VIP bo'lsa taklif).
Har bosqich bir marta (`users.winback_stage` = yuborilgan oxirgi bosqich,
`users.winback_at` = qachon); foydalanuvchi qaytsa (faollik winback_at dan keyin)
bosqich nolga qaytadi. 90 kundan uzoq jim yurganlarga yozilmaydi (spam/bloklash).
Kunduzi 11–19 Toshkent, 20:00 eslatmasidan alohida; bir aylanishda ≤ MAX_PER_RUN.
`process(session, bot, now)` — halqa/test uchun.
"""

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.models import Plan, User, XpLog, utcnow
from services import referral
from services.stats import TASHKENT_OFFSET, _local_date, user_stats

log = logging.getLogger(__name__)

CHECK_INTERVAL = 1200  # 20 daqiqa
HOUR_FROM, HOUR_TO = 11, 19  # Toshkent
STAGES = (3, 7, 30)  # kun
MAX_DAYS = 90  # bundan uzoq jim — yozmaymiz
MAX_PER_RUN = 200
SEND_PAUSE = 0.05


def _local(now: datetime) -> datetime:
    return now + TASHKENT_OFFSET


def _due_hour(now: datetime) -> bool:
    return HOUR_FROM <= _local(now).hour < HOUR_TO


def stage_for(days: int, last_stage: int) -> int:
    """Necha kun jim (days) va oxirgi yuborilgan bosqich → yuboriladigan bosqich (0 = yo'q)."""
    if days > MAX_DAYS:
        return 0
    stage = 0
    for s in STAGES:
        if days >= s:
            stage = s
    return stage if stage > last_stage else 0


def _kb(rows: list[tuple[str, str]]):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

    from services.deploy_notify import webapp_url_versioned

    url = webapp_url_versioned()
    if not url.startswith("https://"):
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t, web_app=WebAppInfo(url=url + h))] for t, h in rows]
    )


def message(stage: int, user: User, st: dict, days: int) -> tuple[str, list[tuple[str, str]]]:
    """(matn HTML, tugmalar). st — user_stats natijasi."""
    name = user.name or "do'stim"
    nxt = st.get("next_lesson") or {}
    lesson = f"«{nxt['title']}»" if nxt.get("title") else "keyingi dars"
    due = st.get("due_count", 0)
    if stage == 3:
        due_line = f"🔁 {due} ta karta takrorlashni kutmoqda.\n" if due else ""
        text = (
            f"{name}, {days} kundan beri ko'rinmadingiz 🐪\n\n"
            f"{due_line}📖 Navbatdagi dars: {lesson}.\n"
            "5 daqiqa yetadi — streak yana yonadi 🔥"
        )
        return text, [("📚 Davom etish", ""), ("🎙 Kunlik savol (1 daqiqa)", "#daily")]
    if stage == 7:
        text = (
            f"{name}, bir hafta o'tdi. Shu orada yangi bo'limlar qo'shildi:\n\n"
            "✍️ <b>Yozuv mashqi</b> — matnni qog'ozga yozing, suratga oling, AI tekshiradi\n"
            "🎧 <b>Tinglab tushunish</b> va 🎤 <b>talaffuz</b> — bepul\n"
            "🤖 <b>AI ustoz</b> — darajangizda jonli suhbat\n\n"
            f"O'rganganingiz joyida: {st.get('words', 0)} so'z, {st.get('lessons', 0)} dars. "
            "Bugun bittasini sinab ko'ring 👇"
        )
        return text, [("✍️ Yozuv mashqi", "#writing"), ("📚 Davom etish", "")]
    text = (
        f"{name}, bir oy bo'ldi. Hammasi saqlanib turibdi: <b>{st.get('words', 0)} so'z</b>, "
        f"<b>{st.get('lessons', 0)} dars</b>, kartalaringiz ham.\n\n"
        f"Qaytish uchun bitta dars yetarli — {lesson}. "
        "Arab tili yugurish emas, yurish: bugun 5 daqiqa 🐪"
    )
    rows = [("📚 Davom etish", "")]
    if referral.trial_available(user):
        text += f"\n\n🎁 Sizga {referral.TRIAL_DAYS} kunlik VIP sinov ochiq — AI ustoz bilan bepul gaplashib ko'ring."
        rows.append(("🎁 VIP sinovni yoqish", "#vip"))
    return text, rows


async def candidates(session: AsyncSession, now: datetime) -> list[tuple[User, int, datetime]]:
    """(user, jim kunlar, oxirgi faollik) — 3+ kun jim, rejasi bor, demo emas."""
    last_xp = (
        select(XpLog.user_id, func.max(XpLog.created_at).label("last"))
        .group_by(XpLog.user_id)
        .subquery()
    )
    plan_first = (
        select(Plan.user_id, func.min(Plan.created_at).label("planned"))
        .group_by(Plan.user_id)
        .subquery()
    )
    rows = (
        await session.execute(
            select(User, last_xp.c.last, plan_first.c.planned)
            .join(plan_first, plan_first.c.user_id == User.id)
            .outerjoin(last_xp, last_xp.c.user_id == User.id)
            .where(User.is_demo == 0, User.tg_id > 0)
        )
    ).all()
    today = _local_date(now)
    out = []
    for user, last, planned in rows:
        activity = max(d for d in (last, planned) if d is not None)
        days = (today - _local_date(activity)).days
        if days >= STAGES[0]:
            out.append((user, days, activity))
    return out


async def process(session: AsyncSession, bot, now: datetime | None = None) -> dict:
    """Bir aylanish. Qaytaradi: {3: n, 7: n, 30: n, "failed": n}."""
    now = now or utcnow()
    out: dict = {3: 0, 7: 0, 30: 0, "failed": 0}
    if not _due_hour(now):
        return out
    sent = 0
    for user, days, activity in await candidates(session, now):
        if sent >= MAX_PER_RUN:
            break
        # Qaytib faol bo'lgan — bosqich nolga
        last_stage = user.winback_stage or 0
        if user.winback_at and activity > user.winback_at:
            last_stage = 0
        stage = stage_for(days, last_stage)
        if not stage:
            continue
        user.winback_stage = stage
        user.winback_at = now  # yetmasa ham qayta urinmaymiz
        st = await user_stats(session, user.id)
        text, rows = message(stage, user, st, days)
        try:
            await bot.send_message(user.tg_id, text, parse_mode="HTML", reply_markup=_kb(rows))
            out[stage] += 1
        except Exception as e:  # botni bloklagan
            out["failed"] += 1
            log.info("qaytarish xabari yetmadi (%s): %r", user.tg_id, e)
        sent += 1
        await session.commit()
        await asyncio.sleep(SEND_PAUSE)
    if settings.admin_id and sent:
        try:
            await bot.send_message(
                settings.admin_id,
                f"↩️ Qaytarish xabarlari: 3 kun — {out[3]}, 7 kun — {out[7]}, 30 kun — {out[30]}, yetmadi — {out['failed']}.",
            )
        except Exception as e:
            log.warning("admin qaytarish xabari yuborilmadi: %r", e)
    return out


async def loop(bot) -> None:
    from db.session import SessionLocal

    while True:
        try:
            if _due_hour(utcnow()):
                async with SessionLocal() as session:
                    await process(session, bot)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("Qaytarish halqasi xatosi: %r", e)
        await asyncio.sleep(CHECK_INTERVAL)
