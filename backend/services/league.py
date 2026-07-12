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


async def seed_demo_rivals(session: AsyncSession) -> None:
    """Demo raqiblarni bir marta yaratadi (bu haftaga XP beradi) — idempotent."""
    existing = (
        await session.execute(select(func.count()).select_from(User).where(User.is_demo == 1))
    ).scalar_one()
    if existing:
        return

    week_start = _week_start_utc()
    for i, (name, base_xp) in enumerate(DEMO_RIVALS):
        user = User(tg_id=-(1000 + i), name=name, is_demo=1)
        session.add(user)
        await session.flush()  # user.id kerak
        # XP'ni hafta ichida bir necha kunga taqsimlab yozamiz
        remaining = base_xp + random.randint(-15, 15)
        day = 0
        while remaining > 0:
            chunk = min(remaining, random.randint(20, 60))
            session.add(
                XpLog(
                    user_id=user.id,
                    amount=chunk,
                    source="demo",
                    created_at=week_start + timedelta(days=day % 6, hours=12),
                )
            )
            remaining -= chunk
            day += 1
    await session.commit()


async def leaderboard(session: AsyncSession, me_id: int) -> dict:
    await seed_demo_rivals(session)
    week_start = _week_start_utc().isoformat()

    rows = (
        await session.execute(
            select(
                User.id,
                User.name,
                User.is_demo,
                func.coalesce(func.sum(XpLog.amount), 0).label("xp"),
            )
            .join(XpLog, XpLog.user_id == User.id)
            .where(XpLog.created_at >= week_start)
            .group_by(User.id)
        )
    ).all()

    ranked = sorted(rows, key=lambda r: r.xp, reverse=True)

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
