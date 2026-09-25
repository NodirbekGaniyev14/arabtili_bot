"""Yangi foydalanuvchi 1-kuni (K20.4).

1. Ilovada: onboarding'dan keyin bosh sahifada «Jamal bilan tanishing» kartasi —
   AI ustoz «tanishish» mavzusida 1 daqiqalik suhbat (bepul 3 javob). Karta yangi
   (3 kun ichida ro'yxatdan o'tgan) va hali ustoz bilan gaplashmagan foydalanuvchiga
   ko'rinadi (`intro_pending`).
2. Botda: ro'yxatdan o'tgan kunning ERTASIGA (10–19 Toshkent) bitta shaxsiy xabar —
   kecha nima qilindi (dars, so'z, ustoz javoblari), bugungi qadam (keyingi dars),
   tugmalar. Bir marta (`users.day2_notice`).
3. K22.1 (voronka: reja tuzganlarning 69% birinchi darsni tugatmasdi): reja tuzilgan
   KUNI, 2 soat o'tib ham birorta dars tugatilmagan bo'lsa — «birinchi dars 5 daqiqa»
   xabari, tugma to'g'ri darsga (`#lesson=<start_lesson>`). 08–22 Toshkent, bir marta
   (`users.first_nudge`); ertasi kuni 2-kun xabari o'zi eslatadi — shuning uchun faqat
   o'sha kun.
"""

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from services import notify_prefs
from db.models import Plan, Progress, TutorTurn, User, utcnow
from services.stats import TASHKENT_OFFSET, user_stats

log = logging.getLogger(__name__)

CHECK_INTERVAL = 1200
HOUR_FROM, HOUR_TO = 10, 19  # Toshkent
NEW_DAYS = 3  # shuncha kun ichida ro'yxatdan o'tgan — «yangi»
INTRO_TOPIC = "tanishish"
SEND_PAUSE = 0.05
NUDGE_AFTER = timedelta(hours=2)  # reja tuzilgach shuncha vaqt dars boshlanmasa
NUDGE_HOUR_FROM, NUDGE_HOUR_TO = 8, 22  # Toshkent


def _local(now: datetime) -> datetime:
    return now + TASHKENT_OFFSET


async def tutor_turns(session: AsyncSession, user_id: int) -> int:
    return int(
        (await session.execute(select(func.count()).select_from(TutorTurn).where(TutorTurn.user_id == user_id))).scalar() or 0
    )


async def intro_pending(session: AsyncSession, user: User, now: datetime | None = None) -> bool:
    """Bosh sahifa kartasi: yangi foydalanuvchi, ustoz bilan hali gaplashmagan."""
    now = now or utcnow()
    if not user.created_at or user.created_at < now - timedelta(days=NEW_DAYS):
        return False
    return await tutor_turns(session, user.id) == 0


def day2_text(user: User, st: dict, turns: int) -> tuple[str, list[tuple[str, str]]]:
    name = user.name or "do'stim"
    nxt = st.get("next_lesson") or {}
    lesson = f"«{nxt['title']}»" if nxt.get("title") else "keyingi dars"
    lessons, words = st.get("lessons", 0), st.get("words", 0)
    if lessons or words or turns:
        did = " · ".join(
            p for p in (
                f"📖 {lessons} dars" if lessons else "",
                f"🆕 {words} so'z" if words else "",
                f"🤖 Jamal bilan {turns} javob" if turns else "",
            ) if p
        )
        yesterday = f"Kecha: {did} — zo'r boshlanish! 👏"
    else:
        yesterday = "Kecha reja tuzdik, mashq hali boshlanmadi — bugun boshlaymiz 🙂"
    text = (
        f"🐪 {name}, Arabiy'da ikkinchi kun!\n\n"
        f"{yesterday}\n\n"
        f"Bugungi qadam: {lesson} — 5 daqiqa. Ketma-ket ikkinchi kun = 🔥 streak boshlanadi."
    )
    rows = [("📚 Darsni boshlash", "")]
    if turns == 0:
        text += "\n\n🤖 Jamal (AI ustoz) sizni kutmoqda — 1 daqiqalik tanishuv suhbati, bepul."
        rows.insert(0, ("🤖 Jamal bilan tanishish", "#tutor"))
    return text, rows


def _kb(rows: list[tuple[str, str]]):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

    from services.deploy_notify import webapp_url_versioned

    url = webapp_url_versioned()
    if not url.startswith("https://"):
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t, web_app=WebAppInfo(url=url + h))] for t, h in rows]
    )


async def process(session: AsyncSession, bot, now: datetime | None = None) -> dict:
    """Kecha (Toshkent sanasi) reja tuzganlarga bitta xabar. {"sent", "failed"}."""
    now = now or utcnow()
    out = {"sent": 0, "failed": 0}
    local = _local(now)
    if not (HOUR_FROM <= local.hour < HOUR_TO):
        return out
    yesterday = local.date() - timedelta(days=1)
    lo = datetime.combine(yesterday, datetime.min.time()) - TASHKENT_OFFSET
    hi = lo + timedelta(days=1)
    first_plan = (
        select(Plan.user_id, func.min(Plan.created_at).label("planned")).group_by(Plan.user_id).subquery()
    )
    rows = (
        await session.execute(
            select(User)
            .join(first_plan, first_plan.c.user_id == User.id)
            .where(
                first_plan.c.planned >= lo, first_plan.c.planned < hi,
                User.is_demo == 0, User.tg_id > 0, User.day2_notice == 0,
            )
        )
    ).scalars().all()
    for user in rows:
        user.day2_notice = 1
        if not notify_prefs.enabled(user, "comeback"):
            continue
        st = await user_stats(session, user.id)
        turns = await tutor_turns(session, user.id)
        text, btn = day2_text(user, st, turns)
        try:
            await bot.send_message(user.tg_id, text, parse_mode="HTML", reply_markup=_kb(btn))
            out["sent"] += 1
        except Exception as e:
            out["failed"] += 1
            log.info("2-kun xabari yetmadi (%s): %r", user.tg_id, e)
        await session.commit()
        await asyncio.sleep(SEND_PAUSE)
    if settings.admin_id and out["sent"] >= 5:
        try:
            await bot.send_message(settings.admin_id, f"🐪 2-kun xabari: {out['sent']} ta yangi foydalanuvchiga yuborildi.")
        except Exception:
            pass
    return out


def _lesson_meta(lesson_id: str) -> dict:
    """Dars nomi, davomiyligi, «bu darsdan keyin» jumlasi — v2 JSON'dan (yo'q bo'lsa bo'sh)."""
    from services.curriculum import load_curriculum, load_lesson_v2

    data = load_lesson_v2(lesson_id) or {}
    cur = load_curriculum().get(lesson_id, {})
    return {
        "title": data.get("title_uz") or cur.get("title_uz") or lesson_id,
        "minutes": int(data.get("duration_min") or 10),
        "can_do": (data.get("can_do_uz") or "").strip(),
    }


def nudge_text(user: User, lesson_id: str) -> tuple[str, list[tuple[str, str]]]:
    name = user.name or "do'stim"
    m = _lesson_meta(lesson_id)
    minutes = min(m["minutes"], 10)
    text = (
        f"🐪 {name}, reja tayyor — qoldi birinchi qadam!\n\n"
        f"📖 «{m['title']}» — {minutes} daqiqa"
        + (f": {m['can_do'][0].lower() + m['can_do'][1:]}" if m["can_do"] else "")
        + "\n\nBugun boshlasangiz, ertaga 🔥 streak boshlanadi. Ko'pchilik shu birinchi darsda «bo'lar ekan-ku» deydi."
    )
    return text, [("📖 Birinchi darsni boshlash", f"#lesson={lesson_id}")]


async def nudge_process(session: AsyncSession, bot, now: datetime | None = None) -> dict:
    """Bugun (Toshkent) reja tuzgan, NUDGE_AFTER o'tib ham dars tugatmaganlarga bitta xabar."""
    now = now or utcnow()
    out = {"sent": 0, "failed": 0}
    local = _local(now)
    if not (NUDGE_HOUR_FROM <= local.hour < NUDGE_HOUR_TO):
        return out
    day_lo = datetime.combine(local.date(), datetime.min.time()) - TASHKENT_OFFSET
    first_plan = (
        select(Plan.user_id, func.min(Plan.created_at).label("planned"), func.min(Plan.id).label("plan_id"))
        .group_by(Plan.user_id).subquery()
    )
    done_users = select(Progress.user_id).distinct()
    rows = (
        await session.execute(
            select(User, first_plan.c.plan_id)
            .join(first_plan, first_plan.c.user_id == User.id)
            .where(
                first_plan.c.planned >= day_lo, first_plan.c.planned <= now - NUDGE_AFTER,
                User.is_demo == 0, User.tg_id > 0, User.first_nudge == 0, User.day2_notice == 0,
                User.id.not_in(done_users),
            )
        )
    ).all()
    for user, plan_id in rows:
        user.first_nudge = 1
        if not notify_prefs.enabled(user, "comeback"):
            continue
        start = (await session.execute(select(Plan.start_lesson).where(Plan.id == plan_id))).scalar_one_or_none() or "a0-01"
        text, btn = nudge_text(user, start)
        try:
            await bot.send_message(user.tg_id, text, parse_mode="HTML", reply_markup=_kb(btn))
            out["sent"] += 1
        except Exception as e:
            out["failed"] += 1
            log.info("birinchi dars turtkisi yetmadi (%s): %r", user.tg_id, e)
        await session.commit()
        await asyncio.sleep(SEND_PAUSE)
    return out


async def loop(bot) -> None:
    from db.session import SessionLocal

    while True:
        try:
            async with SessionLocal() as session:
                if HOUR_FROM <= _local(utcnow()).hour < HOUR_TO:
                    await process(session, bot)
                await nudge_process(session, bot)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("2-kun xabari xatosi: %r", e)
        await asyncio.sleep(CHECK_INTERVAL)

