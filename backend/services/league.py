"""XP reytingi va liga darajalari.

Reyting davrlari: haftalik / oylik / umumiy. Faqat HAQIQIY foydalanuvchilar
(demo raqiblar olib tashlangan).
"""

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


def _week_start_utc() -> datetime:
    """Joriy hafta boshi (dushanba 00:00 Toshkent) — naive UTC."""
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    local = now_utc + TASHKENT_OFFSET
    monday_local = (local - timedelta(days=local.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return monday_local - TASHKENT_OFFSET


LEAGUE_BY_ID = {lg["id"]: lg for lg in LEAGUES}
LEAGUE_ORDER = [lg["id"] for lg in LEAGUES]


def league_for(weekly_xp: int) -> dict:
    """Liga — haftalik XP bo'yicha yorliq (ko'tarilish/tushish yo'q).

    Hamma bitta umumiy reytingda; liga shunchaki shu haftada qancha XP
    to'plaganingizga qarab beriladigan nishon.
    """
    result = LEAGUES[0]
    for lg in LEAGUES:
        if weekly_xp >= lg["min_xp"]:
            result = lg
    return result


def league_by_id(league_id: str) -> dict:
    return LEAGUE_BY_ID.get(league_id or "bronze", LEAGUES[0])


async def _ranked_rows(session: AsyncSession, since: datetime | None):
    """XP bo'yicha saralangan qatorlar — FAQAT haqiqiy foydalanuvchilar.

    `since=None` — butun davr (umumiy reyting).
    """
    q = (
        select(
            User.id,
            User.name,
            User.is_demo,
            func.coalesce(func.sum(XpLog.amount), 0).label("xp"),
        )
        .join(XpLog, XpLog.user_id == User.id)
        .where(User.is_demo == 0)
        .group_by(User.id)
    )
    if since is not None:
        # DIQQAT: datetime obyekti beriladi, isoformat() MATNI emas —
        # aks holda SQLite "2026-07-19 20:00" < "2026-07-19T19:00" deb
        # hisoblab, davr boshidagi XP'ni tushirib qoldiradi.
        q = q.where(XpLog.created_at >= since)
    rows = (await session.execute(q)).all()
    return sorted(rows, key=lambda r: r.xp, reverse=True)


def _month_start_utc() -> datetime:
    """Joriy oy boshi (1-sana 00:00 Toshkent) — naive UTC."""
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    local = now_utc + TASHKENT_OFFSET
    first_local = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return first_local - TASHKENT_OFFSET


def period_start(period: str) -> datetime | None:
    """'week' | 'month' | 'all' -> davr boshi (all uchun None)."""
    if period == "month":
        return _month_start_utc()
    if period == "all":
        return None
    return _week_start_utc()


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


async def top_winners(
    session: AsyncSession,
    since: datetime,
    top_n: int,
    min_participants: int,
) -> list[tuple[int, str, int, int]]:
    """Davr g'oliblari: [(user_id, ism, xp, o'rin), ...].

    Faqat HAQIQIY foydalanuvchilar. Ishtirokchi min_participants dan kam
    bo'lsa — bo'sh ro'yxat (bir kishilik "g'alaba" uchun sovrin yo'q).
    """
    ranked = await _ranked_rows(session, since)
    real = [r for r in ranked if not r.is_demo and r.xp > 0]
    if len(real) < min_participants:
        return []
    return [
        (r.id, r.name or "O'rganuvchi", int(r.xp), pos)
        for pos, r in enumerate(real[:top_n], start=1)
    ]


async def weekly_top3(
    session: AsyncSession, week_start: datetime, min_participants: int = 3
) -> list[tuple[int, str, int, int]]:
    """Haftalik top-3 (top_winners ustidagi qulaylik)."""
    return await top_winners(session, week_start, 3, min_participants)


async def _streaks_by_user(
    session: AsyncSession, user_ids: list[int]
) -> dict[int, int]:
    """user_id -> streak (ketma-ket faol kunlar).

    Bitta so'rov bilan hisoblanadi: oxirgi 90 kunlik XP kunlari olinadi va
    har foydalanuvchi uchun bugundan (yoki kechadan) orqaga sanaladi.
    Muzlatkich (streak freeze) bu yerda hisobga olinmaydi — reyting uchun
    sof ketma-ketlik ko'rsatiladi.
    """
    if not user_ids:
        return {}
    from services.stats import _local_date, _today

    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=90)
    rows = (
        await session.execute(
            select(XpLog.user_id, XpLog.created_at).where(
                XpLog.user_id.in_(user_ids), XpLog.created_at >= since
            )
        )
    ).all()

    days_by_user: dict[int, set] = {}
    for uid, created in rows:
        days_by_user.setdefault(uid, set()).add(_local_date(created))

    today = _today()
    out: dict[int, int] = {}
    for uid, days in days_by_user.items():
        if today in days:
            day = today
        elif (today - timedelta(days=1)) in days:
            day = today - timedelta(days=1)
        else:
            out[uid] = 0
            continue
        streak = 0
        while day in days:
            streak += 1
            day -= timedelta(days=1)
        out[uid] = streak
    return out


async def _levels_by_user(session: AsyncSession, user_ids: list[int]) -> dict[int, str]:
    """user_id -> daraja (oxirgi Plan bo'yicha). Rejasi yo'qlarga A0."""
    if not user_ids:
        return {}
    from db.models import Plan

    rows = (
        await session.execute(
            select(Plan.user_id, Plan.level, Plan.id)
            .where(Plan.user_id.in_(user_ids))
            .order_by(Plan.id)
        )
    ).all()
    return {uid: lvl for uid, lvl, _ in rows}  # keyingi yozuv oldingisini bosadi


async def leaderboard(
    session: AsyncSession, me_id: int, period: str = "week"
) -> dict:
    """Reyting: haftalik / oylik / umumiy. Demo raqiblar yo'q."""
    ranked = await _ranked_rows(session, period_start(period))

    my_xp = next((r.xp for r in ranked if r.id == me_id), 0)
    ids = [r.id for r in ranked] + [me_id]
    levels = await _levels_by_user(session, ids)
    streaks = await _streaks_by_user(session, ids)

    # Hamma bitta umumiy ro'yxatda — liga bo'yicha bo'linish yo'q
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
                "level": levels.get(r.id, "A0"),
                "streak": streaks.get(r.id, 0),
                "is_me": is_me,
                "is_demo": False,
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
                "level": levels.get(me_id, "A0"),
                "streak": streaks.get(me_id, 0),
                "is_me": True,
                "is_demo": False,
            }
        )

    # Liga — faqat HAFTALIK XP bo'yicha yorliq (ko'tarilish/tushish yo'q)
    weekly_xp = my_xp
    if period != "week":
        week_rows = await _ranked_rows(session, _week_start_utc())
        weekly_xp = next((r.xp for r in week_rows if r.id == me_id), 0)

    return {
        "period": period,
        "league": league_for(int(weekly_xp)),
        "all_leagues": LEAGUES,
        "my_rank": my_rank,
        "my_weekly_xp": int(weekly_xp),
        "my_period_xp": int(my_xp),
        "entries": entries,
    }
