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


MAX_FREEZES = 2


def _week_monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


async def resolve_streak(
    session: AsyncSession, user_id: int, active_days: set[date], today: date
) -> tuple[int, int]:
    """Streakni muzlatkichlarni hisobga olib hisoblaydi.

    Muzlatkich (streak freeze) bitta o'tkazib yuborilgan kunni yopadi:
    zanjir uzilmaydi, lekin streak soniga qo'shilmaydi. Haftada +1 beriladi
    (ko'pi bilan 2 ta saqlanadi) va foydalanuvchi qaytib kelganda
    avtomatik ishlatiladi.

    Qaytaradi: (streak, qolgan_muzlatkich).
    """
    from db.models import User

    user = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None:
        return 0, 0

    # Haftalik to'ldirish
    this_week = _week_monday(today).isoformat()
    dirty = False
    if user.freeze_granted_week != this_week:
        user.freeze_granted_week = this_week
        if (user.streak_freezes or 0) < MAX_FREEZES:
            user.streak_freezes = (user.streak_freezes or 0) + 1
        dirty = True

    if not active_days:
        if dirty:
            session.add(user)
            await session.commit()
        return 0, user.streak_freezes or 0

    frozen = {
        date.fromisoformat(s)
        for s in (user.frozen_days or "").split(",")
        if s.strip()
    }
    earliest = min(active_days)
    # Muzlatkich faqat foydalanuvchi BUGUN qaytib kelganda sarflanadi —
    # aks holda hali kuni tugamagan odamning zaxirasi behuda yoqiladi.
    can_spend = today in active_days

    streak = 0
    day = today if today in active_days else today - timedelta(days=1)
    while day >= earliest:
        if day in active_days:
            streak += 1
            day -= timedelta(days=1)
            continue
        if day in frozen:
            day -= timedelta(days=1)
            continue

        # Bo'shliq: keyingi faol kungacha nechta kun yopish kerakligini
        # OLDINDAN sanaymiz. Yetmasa — hech narsa sarflamaymiz (isrof yo'q).
        gap_end = day
        while gap_end >= earliest and gap_end not in active_days:
            gap_end -= timedelta(days=1)
        gap = [
            gap_end + timedelta(days=n + 1)
            for n in range((day - gap_end).days)
        ]
        need = [d for d in gap if d not in frozen]
        if not can_spend or len(need) > (user.streak_freezes or 0):
            break

        user.streak_freezes -= len(need)
        frozen.update(need)
        dirty = True
        day = gap_end

    if dirty:
        user.frozen_days = ",".join(sorted(d.isoformat() for d in frozen))
        session.add(user)
        await session.commit()

    return streak, user.streak_freezes or 0


async def completed_lesson_ids(session: AsyncSession, user_id: int) -> set[str]:
    """TUGATILGAN darslar — mikro-testdan 60%+ olingan urinishlar (spec §11).

    Yiqilgan urinish ham `progress` da saqlanadi, lekin darsni ochilgan
    hisoblamaydi: keyingi dars qulfda qoladi.
    """
    rows = await session.execute(
        select(Progress.lesson_id)
        .where(Progress.user_id == user_id, Progress.passed == 1)
        .distinct()
    )
    return set(rows.scalars())


async def lesson_attempt_count(
    session: AsyncSession, user_id: int, lesson_id: str
) -> int:
    """Shu darsga nechta urinish bo'lgan (o'tgan ham, yiqilgan ham)."""
    from sqlalchemy import func

    return (
        await session.execute(
            select(func.count())
            .select_from(Progress)
            .where(Progress.user_id == user_id, Progress.lesson_id == lesson_id)
        )
    ).scalar_one()


async def profile_extras(session: AsyncSession, user_id: int) -> dict:
    """Profil uchun qo'shimcha: jami XP, eng uzun streak, a'zolik sanasi."""
    from db.models import User

    xp_rows = (
        await session.execute(
            select(XpLog.created_at, XpLog.amount).where(XpLog.user_id == user_id)
        )
    ).all()
    total_xp = sum(a for _, a in xp_rows)

    user = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    member_since = user.created_at.date().isoformat() if user else ""

    # Eng uzun streak — muzlatilgan kunlar zanjirni uzmaydi
    frozen = {
        date.fromisoformat(s)
        for s in ((user.frozen_days if user else "") or "").split(",")
        if s.strip()
    }
    active_days = sorted({_local_date(dt) for dt, _ in xp_rows})
    longest = 0
    run = 0
    prev = None
    for d in active_days:
        if prev is not None:
            gap = {prev + timedelta(days=i) for i in range(1, (d - prev).days)}
            joined = (d - prev).days == 1 or (gap and gap <= frozen)
            run = run + 1 if joined else 1
        else:
            run = 1
        longest = max(longest, run)
        prev = d

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
    streak, freezes_left = await resolve_streak(session, user_id, active_days, today)

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
        "streak_freezes": freezes_left,
        "xp_today": xp_today,
        "words": words,
        "lessons": len(v2_done),
        "accuracy": accuracy,
        "due_count": due_count,
        "next_lesson": next_lesson,
    }
