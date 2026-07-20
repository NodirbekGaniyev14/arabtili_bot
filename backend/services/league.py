"""Haftalik liga — XP reytingi va liga darajalari.

Reyting jonli ko'rinishi uchun bir nechta demo raqib qo'shiladi (is_demo=1).
Ular haqiqiy foydalanuvchilar bilan aralashmaydi (statistika/yutuqlar alohida).
"""

import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import User, XpLog
from services.stats import TASHKENT_OFFSET

# Liga darajalari — haftalik XP bo'yicha (past→yuqori)
LEAGUES = [
    {"id": "bronze", "name": "Bronza", "icon": "🥉", "min_xp": 0},
    {"id": "silver", "name": "Kumush", "icon": "🥈", "min_xp": 100},
    {"id": "gold", "name": "Oltin", "icon": "🥇", "min_xp": 300},
    {"id": "emerald", "name": "Zumrad", "icon": "💎", "min_xp": 600},
]

DEMO_RIVALS = [
    ("Diyor", 340),
    ("Malika", 285),
    ("Sardor", 210),
    ("Nilufar", 155),
    ("Jasur", 120),
    ("Kamola", 80),
    ("Bekzod", 45),
]


def _week_start_utc() -> datetime:
    """Joriy hafta boshi (dushanba 00:00 Toshkent) — naive UTC."""
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    local = now_utc + TASHKENT_OFFSET
    monday_local = (local - timedelta(days=local.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return monday_local - TASHKENT_OFFSET


def league_for(weekly_xp: int) -> dict:
    result = LEAGUES[0]
    for lg in LEAGUES:
        if weekly_xp >= lg["min_xp"]:
            result = lg
    return result


def _fill_week_xp(session: AsyncSession, user_id: int, base_xp: int, week_start: datetime) -> None:
    """Demo raqibga hafta ichiga taqsimlangan XP yozadi."""
    remaining = base_xp + random.randint(-15, 15)
    day = 0
    while remaining > 0:
        chunk = min(remaining, random.randint(20, 60))
        session.add(
            XpLog(
                user_id=user_id,
                amount=chunk,
                source="demo",
                created_at=week_start + timedelta(days=day % 6, hours=12),
            )
        )
        remaining -= chunk
        day += 1


async def seed_demo_rivals(session: AsyncSession) -> None:
    """Demo raqiblarni yaratadi va HAR HAFTA ularga yangi XP yozadi.

    Avval faqat bir marta seed qilinardi — natijada ikkinchi haftadan
    boshlab reyting bo'shab qolardi (haftalik so'rov XpLog'ga tayanadi).
    """
    week_start = _week_start_utc()

    demos = (
        await session.execute(select(User).where(User.is_demo == 1))
    ).scalars().all()

    if not demos:
        for i, (name, base_xp) in enumerate(DEMO_RIVALS):
            user = User(tg_id=-(1000 + i), name=name, is_demo=1)
            session.add(user)
            await session.flush()  # user.id kerak
            _fill_week_xp(session, user.id, base_xp, week_start)
        await session.commit()
        return

    # Mavjud demo raqiblarda shu haftaga XP bormi?
    have_xp = set(
        (
            await session.execute(
                select(XpLog.user_id)
                .where(XpLog.created_at >= week_start, XpLog.source == "demo")
                .distinct()
            )
        ).scalars().all()
    )
    base_by_name = dict(DEMO_RIVALS)
    added = False
    for u in demos:
        if u.id in have_xp:
            continue
        _fill_week_xp(session, u.id, base_by_name.get(u.name, 120), week_start)
        added = True
    if added:
        await session.commit()


async def _ranked_rows(session: AsyncSession, week_start: datetime):
    """Haftalik XP bo'yicha saralangan qatorlar (demo raqiblar ham kiradi)."""
    rows = (
        await session.execute(
            select(
                User.id,
                User.name,
                User.is_demo,
                func.coalesce(func.sum(XpLog.amount), 0).label("xp"),
            )
            .join(XpLog, XpLog.user_id == User.id)
            # DIQQAT: datetime obyekti beriladi, isoformat() MATNI emas —
            # aks holda SQLite "2026-07-19 20:00" < "2026-07-19T19:00" deb
            # hisoblab, hafta boshi kunidagi XP'ni tushirib qoldiradi.
            .where(XpLog.created_at >= week_start)
            .group_by(User.id)
        )
    ).all()
    return sorted(rows, key=lambda r: r.xp, reverse=True)


async def refresh_ranks(session: AsyncSession) -> list[tuple[User, int, int]]:
    """O'rinlarni qayta hisoblab, tushib ketganlarni qaytaradi.

    Qaytaradi: [(user, eski_o'rin, yangi_o'rin), ...] — faqat HAQIQIY
    foydalanuvchilar va faqat o'rni yomonlashganlar.
    """
    ranked = await _ranked_rows(session, _week_start_utc())
    if not ranked:
        return []

    new_rank = {r.id: pos for pos, r in enumerate(ranked, start=1)}
    real_ids = [r.id for r in ranked if not r.is_demo]
    if not real_ids:
        return []

    users = (
        await session.execute(select(User).where(User.id.in_(real_ids)))
    ).scalars().all()

    dropped: list[tuple[User, int, int]] = []
    for u in users:
        nr = new_rank.get(u.id)
        if nr is None:
            continue
        old = u.last_rank or 0
        if old and nr > old:
            dropped.append((u, old, nr))
        u.last_rank = nr
        session.add(u)
    await session.commit()
    return dropped


async def weekly_top3(
    session: AsyncSession, week_start: datetime, min_participants: int = 3
) -> list[tuple[int, str, int, int]]:
    """O'tgan hafta g'oliblari: [(user_id, ism, xp, o'rin), ...].

    Faqat HAQIQIY foydalanuvchilar. Ishtirokchi kam bo'lsa — bo'sh ro'yxat
    (bir kishilik "g'alaba" uchun sertifikat berilmaydi).
    """
    ranked = await _ranked_rows(session, week_start)
    real = [r for r in ranked if not r.is_demo and r.xp > 0]
    if len(real) < min_participants:
        return []
    return [
        (r.id, r.name or "O'rganuvchi", int(r.xp), pos)
        for pos, r in enumerate(real[:3], start=1)
    ]


async def leaderboard(session: AsyncSession, me_id: int) -> dict:
    await seed_demo_rivals(session)
    ranked = await _ranked_rows(session, _week_start_utc())

    my_xp = next((r.xp for r in ranked if r.id == me_id), 0)

    entries = []
    my_rank = None
    for pos, r in enumerate(ranked, start=1):
        is_me = r.id == me_id
        if is_me:
            my_rank = pos
        entries.append(
            {
                "rank": pos,
                "name": r.name or "Foydalanuvchi",
                "xp": int(r.xp),
                "is_me": is_me,
                "is_demo": bool(r.is_demo),
            }
        )

    # Foydalanuvchi reytingda bo'lmasa (0 XP) — ro'yxat oxiriga qo'shamiz
    if my_rank is None:
        my_rank = len(entries) + 1
        entries.append(
            {
                "rank": my_rank,
                "name": "Siz",
                "xp": 0,
                "is_me": True,
                "is_demo": False,
            }
        )

    return {
        "league": league_for(int(my_xp)),
        "all_leagues": LEAGUES,
        "my_rank": my_rank,
        "my_weekly_xp": int(my_xp),
        "entries": entries,
    }
