"""Admin haftalik digest (K20.3) — dushanba ~09:30 Toshkent, hafta uchun bir marta.

O'tgan hafta [dushanba, dushanba): foydalanuvchilar (yangi/faol/qaytgan), darslar va
XP, speaking bo'limlari, yozuv mashqi, VIP to'lovlari, AI sarfi, ustoz sifati
(👍/👎 + so'nggi izohlar), reyting g'oliblari, o'tgan haftaga nisbatan ▲/▼.
Marker: Meta «admin_digest_done» = hafta kaliti. `weekly_loop` chaqiradi (`maybe_send`).
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.models import (
    AiUsage,
    DailySpeaking,
    DrillResult,
    ListeningResult,
    Meta,
    MockResult,
    PaymentRequest,
    TutorRating,
    TutorTurn,
    User,
    WeeklyAward,
    WritingResult,
    XpLog,
    utcnow,
)
from services import ai_usage
from services.speaking_report import week_key, week_label, week_start_utc
from services.stats import TASHKENT_OFFSET

log = logging.getLogger(__name__)

MARKER = "admin_digest_done"
SEND_HOUR = 9  # Toshkent; 09:00 reyting yakunidan keyin


def _local(now: datetime) -> datetime:
    return now + TASHKENT_OFFSET


def _delta(cur: int, prev: int) -> str:
    if cur == prev:
        return ""
    return f" ▲{cur - prev}" if cur > prev else f" ▼{prev - cur}"


async def _count(session: AsyncSession, stmt) -> int:
    return int((await session.execute(stmt)).scalar() or 0)


async def week_numbers(session: AsyncSession, since: datetime, until: datetime) -> dict:
    """[since, until) uchun raqamlar."""
    d: dict = {}
    d["new_users"] = await _count(session, select(func.count()).select_from(User).where(
        User.is_demo == 0, User.created_at >= since, User.created_at < until))
    d["active"] = await _count(session, select(func.count(func.distinct(XpLog.user_id))).where(
        XpLog.created_at >= since, XpLog.created_at < until))
    d["returned"] = await _count(session, select(func.count()).select_from(User).where(
        User.winback_at >= since, User.winback_at < until,
        User.id.in_(select(XpLog.user_id).where(XpLog.created_at >= since, XpLog.created_at < until))))
    d["lessons"] = await _count(session, select(func.count()).select_from(XpLog).where(
        XpLog.created_at >= since, XpLog.created_at < until, XpLog.source.like("lesson:%")))
    d["xp"] = await _count(session, select(func.coalesce(func.sum(XpLog.amount), 0)).where(
        XpLog.created_at >= since, XpLog.created_at < until))
    d["chat"] = await _count(session, select(func.count()).select_from(TutorTurn).where(
        TutorTurn.mode == "chat", TutorTurn.created_at >= since, TutorTurn.created_at < until))
    d["chat_users"] = await _count(session, select(func.count(func.distinct(TutorTurn.user_id))).where(
        TutorTurn.created_at >= since, TutorTurn.created_at < until))
    d["voice"] = await _count(session, select(func.count()).select_from(TutorTurn).where(
        TutorTurn.voice == 1, TutorTurn.created_at >= since, TutorTurn.created_at < until))
    d["mocks"] = await _count(session, select(func.count()).select_from(MockResult).where(
        MockResult.created_at >= since, MockResult.created_at < until))
    day_from, day_to = _local(since).date().isoformat(), _local(until).date().isoformat()
    d["daily"] = await _count(session, select(func.count()).select_from(DailySpeaking).where(
        DailySpeaking.day >= day_from, DailySpeaking.day < day_to))
    d["drills"] = await _count(session, select(func.count()).select_from(DrillResult).where(
        DrillResult.created_at >= since, DrillResult.created_at < until))
    d["listens"] = await _count(session, select(func.count()).select_from(ListeningResult).where(
        ListeningResult.created_at >= since, ListeningResult.created_at < until))
    d["writings"] = await _count(session, select(func.count()).select_from(WritingResult).where(
        WritingResult.attempts > 0, WritingResult.updated_at >= since, WritingResult.updated_at < until))
    pay_n, pay_sum = (await session.execute(
        select(func.count(), func.coalesce(func.sum(PaymentRequest.amount), 0)).where(
            PaymentRequest.status == "approved", PaymentRequest.decided_at >= since, PaymentRequest.decided_at < until)
    )).one()
    d["pay_n"], d["pay_sum"] = int(pay_n), int(pay_sum)
    r_n, r_good = (await session.execute(
        select(func.count(), func.coalesce(func.sum(TutorRating.good), 0)).where(
            TutorRating.created_at >= since, TutorRating.created_at < until)
    )).one()
    d["rating_n"], d["rating_good"] = int(r_n), int(r_good)
    calls, t_in, t_out, c_read, c_write = (await session.execute(
        select(
            func.count(),
            func.coalesce(func.sum(AiUsage.tokens_in), 0),
            func.coalesce(func.sum(AiUsage.tokens_out), 0),
            func.coalesce(func.sum(AiUsage.cache_read), 0),
            func.coalesce(func.sum(AiUsage.cache_write), 0),
        ).where(AiUsage.created_at >= since, AiUsage.created_at < until)
    )).one()
    d["ai_calls"] = int(calls)
    d["ai_cost"] = ai_usage.cost_usd({"in": t_in, "out": t_out, "cache_read": c_read, "cache_write": c_write})
    return d


async def build(session: AsyncSession, now: datetime | None = None) -> str:
    now = now or utcnow()
    this_monday = week_start_utc(now)
    prev_monday = this_monday - timedelta(days=7)
    cur = await week_numbers(session, prev_monday, this_monday)
    prev = await week_numbers(session, prev_monday - timedelta(days=7), prev_monday)
    vip_active = await _count(session, select(func.count()).select_from(User).where(User.vip_until > now))
    pending = await _count(session, select(func.count()).select_from(PaymentRequest).where(PaymentRequest.status == "pending"))
    total_users = await _count(session, select(func.count()).select_from(User).where(User.is_demo == 0))
    bad_rows = (await session.execute(
        select(TutorRating.mode, TutorRating.topic, TutorRating.comment).where(
            TutorRating.good == 0, TutorRating.created_at >= prev_monday, TutorRating.created_at < this_monday
        ).order_by(TutorRating.id.desc()).limit(5)
    )).all()
    winners = (await session.execute(
        select(WeeklyAward.rank, User.name, WeeklyAward.weekly_xp)
        .join(User, User.id == WeeklyAward.user_id)
        .where(WeeklyAward.period == "week", WeeklyAward.week_start == week_key(prev_monday))
        .order_by(WeeklyAward.rank)
    )).all()

    voice_pct = round(cur["voice"] * 100 / cur["chat"]) if cur["chat"] else 0
    q_line = (
        f"👍 {round(cur['rating_good'] * 100 / cur['rating_n'])}% ({cur['rating_n']} baho)" if cur["rating_n"] else "baho yo'q"
    )
    bad = "".join(f"\n   👎 {m} · {t or '—'}" + (f": {c[:60]}" if c else "") for m, t, c in bad_rows)
    win = " · ".join(f"{'🥇🥈🥉'[r - 1] if r <= 3 else '🏅'} {n} ({xp})" for r, n, xp in winners) or "sovrin berilmadi (kam ishtirokchi)"
    pay = f"{cur['pay_n']} ta · {cur['pay_sum']:,} so'm".replace(",", " ")

    return (
        f"📊 <b>Haftalik digest</b> · {week_label(prev_monday)}\n\n"
        f"👥 <b>Foydalanuvchilar</b> (jami {total_users})\n"
        f"• Yangi: <b>{cur['new_users']}</b>{_delta(cur['new_users'], prev['new_users'])}"
        f" · Faol: <b>{cur['active']}</b>{_delta(cur['active'], prev['active'])}"
        f" · Qaytgan (winback): {cur['returned']}\n"
        f"• Darslar: {cur['lessons']}{_delta(cur['lessons'], prev['lessons'])} · XP: {cur['xp']}{_delta(cur['xp'], prev['xp'])}\n\n"
        f"🗣 <b>Speaking</b>\n"
        f"• Suhbat: {cur['chat']} javob{_delta(cur['chat'], prev['chat'])} · {cur['chat_users']} o'quvchi · 🎤 {voice_pct}%\n"
        f"• Mock: {cur['mocks']} · Kunlik savol: {cur['daily']}{_delta(cur['daily'], prev['daily'])}"
        f" · Talaffuz: {cur['drills']} · Tinglash: {cur['listens']} · ✍️ Yozuv: {cur['writings']}\n"
        f"• Sifat: {q_line}{bad}\n\n"
        f"👑 <b>VIP</b>\n"
        f"• Faol: {vip_active} · Bu hafta to'lov: {pay}{_delta(cur['pay_n'], prev['pay_n'])} · Kutayotgan chek: {pending}\n"
        f"• AI sarfi: ${cur['ai_cost']:.2f} ({cur['ai_calls']} chaqiruv)\n\n"
        f"🏆 <b>Reyting</b>: {win}\n\n"
        f"Batafsil: /admin · /ustoz · /retention"
    )


async def maybe_send(bot, now: datetime | None = None) -> bool:
    """Dushanba ≥ 09:00 Toshkent, hafta uchun bir marta. Yuborilsa True."""
    from db.session import SessionLocal

    now = now or utcnow()
    local = _local(now)
    if not settings.admin_id or local.weekday() != 0 or local.hour < SEND_HOUR:
        return False
    key = week_key(week_start_utc(now))
    async with SessionLocal() as session:
        marker = (await session.execute(select(Meta).where(Meta.key == MARKER))).scalar_one_or_none()
        if marker and marker.value == key:
            return False
        text = await build(session, now)
        if marker:
            marker.value = key
        else:
            marker = Meta(key=MARKER, value=key)
        session.add(marker)
        await session.commit()
    try:
        await bot.send_message(settings.admin_id, text, parse_mode="HTML")
    except Exception as e:
        log.warning("admin digest yuborilmadi: %r", e)
        return False
    return True
