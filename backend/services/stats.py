"""Foydalanuvchi statistikasi: streak, XP, so'zlar, keyingi dars."""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Plan, Progress, UserWord, XpLog
from services.course import count_vocab, next_lesson as course_next_lesson

TASHKENT_OFFSET = timedelta(hours=5)


def _local_date(dt_naive_utc: datetime) -> date:
    return (dt_naive_utc + TASHKENT_OFFSET).date()


def _today() -> date:
    return _local_date(datetime.now(timezone.utc).replace(tzinfo=None))


async def completed_lesson_ids(session: AsyncSession, user_id: int) -> set[str]:
    rows = await session.execute(
        select(Progress.lesson_id).where(Progress.user_id == user_id).distinct()
    )
    return set(rows.scalars())


async def profile_extras(session: AsyncSession, user_id: int) -> dict:
    """Profil uchun qo'shimcha: jami XP, eng uzun streak, a'zolik sanasi."""
    from db.models import User

    xp_rows = (
        await session.execute(
            select(XpLog.created_at, XpLog.amount).where(XpLog.user_id == user_id)
        )
    ).all()
    total_xp = sum(a for _, a in xp_rows)

    # Eng uzun streak — faol kunlarning eng uzun ketma-ketligi
    active_days = sorted({_local_date(dt) for dt, _ in xp_rows})
    longest = 0
    run = 0
    prev = None
    for d in active_days:
        if prev is not None and (d - prev).days == 1:
            run += 1
        else:
            run = 1
        longest = max(longest, run)
        prev = d

    user = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    member_since = user.created_at.date().isoformat() if user else ""

    return {
        "total_xp": total_xp,
        "longest_streak": longest,
        "member_since": member_since,
    }


async def user_stats(
    session: AsyncSession, user_id: int, plan_order: list[str] | None = None
) -> dict:
    done = await completed_lesson_ids(session, user_id)

    # Foydalanuvchi rejasi — v2 kurs yo'lini boshlash nuqtasi
    plan = (
        await session.execute(
            select(Plan).where(Plan.user_id == user_id).order_by(Plan.id.desc()).limit(1)
        )
    ).scalar_one_or_none()
    start_lesson = plan.start_lesson if plan else "a0-01"

    # Aniqlik
    rows = (
        await session.execute(select(Progress).where(Progress.user_id == user_id))
    ).scalars().all()
    total_answers = sum(p.total for p in rows)
    correct_answers = sum(p.correct for p in rows)
    accuracy = round(100 * correct_answers / total_answers) if total_answers else 0

    # Faqat v2 kurs darslarini sanaymiz (eski v1 progress statistikani shishirmasin)
    from services.curriculum import load_curriculum

    v2_ids = load_curriculum()
    v2_done = [lid for lid in done if lid in v2_ids]

    # So'zlar (tugatilgan v2 darslardagi yangi so'zlar)
    words = sum(count_vocab(lid) for lid in v2_done)

    # XP va streak
    xp_rows = (
        await session.execute(
            select(XpLog.created_at, XpLog.amount).where(XpLog.user_id == user_id)
        )
    ).all()
    today = _today()
    xp_today = sum(a for dt, a in xp_rows if _local_date(dt) == today)

    active_days = {_local_date(dt) for dt, _ in xp_rows}
    streak = 0
    day = today if today in active_days else today - timedelta(days=1)
    while day in active_days:
        streak += 1
        day -= timedelta(days=1)

    # Bugun takrorlanishi kerak bo'lgan kartalar
    due_rows = await session.execute(
        select(UserWord.id).where(
            UserWord.user_id == user_id, UserWord.due_date <= today.isoformat()
        )
    )
    due_count = len(due_rows.scalars().all())

    # Keyingi dars — v2 kurs yo'li bo'yicha (yozilgan darslardan)
    next_lesson = course_next_lesson(done, start_lesson)

    return {
        "streak": streak,
        "xp_today": xp_today,
        "words": words,
        "lessons": len(v2_done),
        "accuracy": accuracy,
        "due_count": due_count,
        "next_lesson": next_lesson,
    }
