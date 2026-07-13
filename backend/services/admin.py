"""Admin statistikasi — bot foydalanuvchilari va faollik haqida ma'lumot."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Achievement, Plan, Progress, User, UserWord, XpLog
from services.stats import TASHKENT_OFFSET, _local_date, _today


def _day_start_utc(d) -> str:
    """Toshkent sanasi 00:00 → naive UTC ISO (xp_log/created_at bilan solishtirish uchun)."""
    local_midnight = datetime(d.year, d.month, d.day)
    return (local_midnight - TASHKENT_OFFSET).isoformat()


async def overview(session: AsyncSession) -> str:
    today = _today()
    today_start = _day_start_utc(today)
    week_start = _day_start_utc(today - timedelta(days=6))

    async def scalar(q):
        return (await session.execute(q)).scalar_one()

    real = User.is_demo == 0

    total_users = await scalar(
        select(func.count()).select_from(User).where(real)
    )
    onboarded = await scalar(
        select(func.count(func.distinct(Plan.user_id)))
    )
    new_today = await scalar(
        select(func.count()).select_from(User).where(
            real, User.created_at >= today_start
        )
    )
    new_week = await scalar(
        select(func.count()).select_from(User).where(
            real, User.created_at >= week_start
        )
    )

    active_today = await scalar(
        select(func.count(func.distinct(XpLog.user_id)))
        .select_from(XpLog)
        .join(User, User.id == XpLog.user_id)
        .where(real, XpLog.created_at >= today_start)
    )
    active_week = await scalar(
        select(func.count(func.distinct(XpLog.user_id)))
        .select_from(XpLog)
        .join(User, User.id == XpLog.user_id)
        .where(real, XpLog.created_at >= week_start)
    )

    lessons_done = await scalar(
        select(func.count())
        .select_from(Progress)
        .join(User, User.id == Progress.user_id)
        .where(real)
    )
    total_xp = await scalar(
        select(func.coalesce(func.sum(XpLog.amount), 0))
        .select_from(XpLog)
        .join(User, User.id == XpLog.user_id)
        .where(real)
    )
    reviews = await scalar(
        select(func.count())
        .select_from(XpLog)
        .join(User, User.id == XpLog.user_id)
        .where(real, XpLog.source == "review")
    )
    badges = await scalar(
        select(func.count())
        .select_from(Achievement)
        .join(User, User.id == Achievement.user_id)
        .where(real)
    )
    words = await scalar(
        select(func.count())
        .select_from(UserWord)
        .join(User, User.id == UserWord.user_id)
        .where(real)
    )

    # Daraja taqsimoti (har foydalanuvchining oxirgi rejasi)
    latest_plan = (
        select(Plan.user_id, func.max(Plan.id).label("mid"))
        .group_by(Plan.user_id)
        .subquery()
    )
    level_rows = (
        await session.execute(
            select(Plan.level, func.count())
            .join(latest_plan, latest_plan.c.mid == Plan.id)
            .group_by(Plan.level)
        )
    ).all()
    level_dist = " · ".join(f"{lvl}: {cnt}" for lvl, cnt in sorted(level_rows)) or "—"

    return (
        "📊 <b>Arabiy — Admin panel</b>\n\n"
        "👥 <b>Foydalanuvchilar</b>\n"
        f"• Jami: <b>{total_users}</b>\n"
        f"• Ro'yxatdan o'tgan (reja tuzgan): <b>{onboarded}</b>\n"
        f"• Bugun yangi: <b>{new_today}</b> · 7 kunda: <b>{new_week}</b>\n\n"
        "🔥 <b>Faollik</b>\n"
        f"• Bugun faol: <b>{active_today}</b>\n"
        f"• 7 kunda faol: <b>{active_week}</b>\n\n"
        "📚 <b>O'quv</b>\n"
        f"• Tugatilgan darslar: <b>{lessons_done}</b>\n"
        f"• Takror kartalari: <b>{words}</b>\n"
        f"• Takror mashqlari: <b>{reviews}</b>\n"
        f"• Jami XP: <b>{total_xp}</b>\n"
        f"• Berilgan yutuqlar: <b>{badges}</b>\n\n"
        "🎯 <b>Darajalar</b>\n"
        f"• {level_dist}\n\n"
        "ℹ️ Buyruqlar: /stats /users /user /broadcast"
    )


async def recent_users(session: AsyncSession, limit: int = 15) -> str:
    rows = (
        await session.execute(
            select(User)
            .where(User.is_demo == 0)
            .order_by(User.id.desc())
            .limit(limit)
        )
    ).scalars().all()

    if not rows:
        return "Hozircha foydalanuvchilar yo'q."

    lines = [f"👥 <b>Oxirgi {len(rows)} foydalanuvchi</b>\n"]
    for u in rows:
        # Har biriga qisqa: daraja, darslar, XP
        plan = (
            await session.execute(
                select(Plan.level)
                .where(Plan.user_id == u.id)
                .order_by(Plan.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        lessons = (
            await session.execute(
                select(func.count()).select_from(Progress).where(
                    Progress.user_id == u.id
                )
            )
        ).scalar_one()
        joined = _local_date(u.created_at).isoformat()
        uname = f"@{u.username}" if u.username else "—"
        name = u.name or "Ismsiz"
        level = plan or "reja yo‘q"
        lines.append(
            f"• <b>{name}</b> ({uname}) · ID <code>{u.tg_id}</code>\n"
            f"  {level} · {lessons} dars · {joined}"
        )
    return "\n".join(lines)


async def user_detail(session: AsyncSession, tg_id: int) -> str:
    user = (
        await session.execute(select(User).where(User.tg_id == tg_id))
    ).scalar_one_or_none()
    if user is None:
        return f"❌ <code>{tg_id}</code> ID'li foydalanuvchi topilmadi."

    plan = (
        await session.execute(
            select(Plan)
            .where(Plan.user_id == user.id)
            .order_by(Plan.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    lessons = (
        await session.execute(
            select(func.count()).select_from(Progress).where(
                Progress.user_id == user.id
            )
        )
    ).scalar_one()
    total_xp = (
        await session.execute(
            select(func.coalesce(func.sum(XpLog.amount), 0)).where(
                XpLog.user_id == user.id
            )
        )
    ).scalar_one()
    words = (
        await session.execute(
            select(func.count()).select_from(UserWord).where(
                UserWord.user_id == user.id
            )
        )
    ).scalar_one()
    badges = (
        await session.execute(
            select(func.count()).select_from(Achievement).where(
                Achievement.user_id == user.id
            )
        )
    ).scalar_one()
    last_xp = (
        await session.execute(
            select(func.max(XpLog.created_at)).where(XpLog.user_id == user.id)
        )
    ).scalar_one()

    uname = f"@{user.username}" if user.username else "—"
    plan_line = (
        f"{plan.level} → {plan.target_level} ({plan.target_date}), "
        f"kunlik {plan.daily_xp_goal} XP"
        if plan
        else "reja tuzmagan"
    )
    last = _local_date(last_xp).isoformat() if last_xp else "—"

    return (
        f"👤 <b>{user.name or 'Ismsiz'}</b> ({uname})\n"
        f"ID: <code>{user.tg_id}</code>\n"
        f"Ro'yxatdan o'tgan: {_local_date(user.created_at).isoformat()}\n"
        f"Oxirgi faollik: {last}\n\n"
        f"📋 Reja: {plan_line}\n"
        f"📚 Darslar: {lessons}\n"
        f"🔁 Takror kartalari: {words}\n"
        f"💎 Jami XP: {total_xp}\n"
        f"🏆 Yutuqlar: {badges}"
    )


async def all_real_tg_ids(session: AsyncSession) -> list[int]:
    return list(
        (
            await session.execute(
                select(User.tg_id).where(User.is_demo == 0)
            )
        ).scalars()
    )
