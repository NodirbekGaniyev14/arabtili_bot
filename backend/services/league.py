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

# Haftalik harakat qoidalari
PROMOTE_TOP = 3          # ligadagi eng yaxshi 3 kishi yuqoriga ko'tariladi
RELEGATE_BOTTOM = 3      # eng pastdagi 3 kishi pastga tushadi
MIN_FOR_RELEGATION = 8   # ligada shundan kam ishtirokchi bo'lsa — tushirilmaydi
MIN_XP_TO_PROMOTE = 50   # nol-faol odam "g'olib" bo'lib ko'tarilmasin


def league_for(weekly_xp: int) -> dict:
    """XP bo'yicha liga (faqat BOSHLANG'ICH tayinlash uchun)."""
    result = LEAGUES[0]
    for lg in LEAGUES:
        if weekly_xp >= lg["min_xp"]:
            result = lg
    return result


def league_by_id(league_id: str) -> dict:
    return LEAGUE_BY_ID.get(league_id or "bronze", LEAGUES[0])


def _shift(league_id: str, step: int) -> str:
    i = LEAGUE_ORDER.index(league_id) if league_id in LEAGUE_ORDER else 0
    return LEAGUE_ORDER[max(0, min(len(LEAGUE_ORDER) - 1, i + step))]


async def league_standings(
    session: AsyncSession, league_id: str, since: datetime | None
) -> list:
    """Bitta liga ichidagi saralangan qatorlar."""
    rows = await _ranked_rows(session, since)
    ids = {
        uid
        for uid, lg in (
            await session.execute(select(User.id, User.league_id).where(User.is_demo == 0))
        ).all()
        if (lg or "bronze") == league_id
    }
    return [r for r in rows if r.id in ids]


async def apply_league_movement(
    session: AsyncSession, week_start: datetime
) -> list[tuple[User, str, str]]:
    """Hafta yakunida ligalarni qayta taqsimlaydi.

    Har liga ichida haftalik XP bo'yicha saralanadi: yuqori PROMOTE_TOP
    ko'tariladi, quyi RELEGATE_BOTTOM tushadi. Kichik ligada (ishtirokchi
    MIN_FOR_RELEGATION dan kam) hech kim tushirilmaydi — 3 kishilik
    guruhda "oxirgi o'rin" jazoga loyiq emas.

    Qaytaradi: [(user, eski_liga, yangi_liga), ...]
    """
    users = (
        await session.execute(select(User).where(User.is_demo == 0))
    ).scalars().all()
    if not users:
        return []

    xp_by_id = {
        r.id: int(r.xp) for r in await _ranked_rows(session, week_start)
    }

    by_league: dict[str, list[User]] = {}
    for u in users:
        by_league.setdefault(u.league_id or "bronze", []).append(u)

    moved: list[tuple[User, str, str]] = []
    for league_id, members in by_league.items():
        members.sort(key=lambda u: xp_by_id.get(u.id, 0), reverse=True)
        top_i = LEAGUE_ORDER.index(league_id) if league_id in LEAGUE_ORDER else 0

        # Ko'tarilish — eng yuqori daraja bo'lmasa va XP yetarli bo'lsa
        if top_i < len(LEAGUE_ORDER) - 1:
            for u in members[:PROMOTE_TOP]:
                if xp_by_id.get(u.id, 0) >= MIN_XP_TO_PROMOTE:
                    new = _shift(league_id, +1)
                    moved.append((u, league_id, new))
                    u.league_id = new
                    session.add(u)

        # Tushish — guruh yetarlicha katta bo'lsa va eng past daraja bo'lmasa
        if top_i > 0 and len(members) >= MIN_FOR_RELEGATION:
            for u in members[-RELEGATE_BOTTOM:]:
                if any(u.id == m.id for m, _, _ in moved):
                    continue  # ko'tarilganni tushirmaymiz
                new = _shift(league_id, -1)
                moved.append((u, league_id, new))
                u.league_id = new
                session.add(u)

    if moved:
        await session.commit()
    return moved


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
    league_of = {
        uid: (lg or "bronze")
        for uid, lg in (
            await session.execute(select(User.id, User.league_id))
        ).all()
    }

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
                "league": league_of.get(r.id, "bronze"),
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
                "league": league_of.get(me_id, "bronze"),
                "is_me": True,
                "is_demo": False,
            }
        )

    weekly_xp = my_xp
    week_rows = ranked
    if period != "week":
        week_rows = await _ranked_rows(session, _week_start_utc())
        weekly_xp = next((r.xp for r in week_rows if r.id == me_id), 0)

    # Liga — SAQLANGAN daraja (haftalik ko'tarilish/tushish natijasi)
    my_league_id = league_of.get(me_id, "bronze")
    cohort = [r for r in week_rows if league_of.get(r.id, "bronze") == my_league_id]
    my_league_rank = next(
        (i for i, r in enumerate(cohort, start=1) if r.id == me_id), len(cohort) + 1
    )
    size = max(len(cohort), 1)
    top_i = LEAGUE_ORDER.index(my_league_id) if my_league_id in LEAGUE_ORDER else 0

    in_promote = (
        top_i < len(LEAGUE_ORDER) - 1
        and my_league_rank <= PROMOTE_TOP
        and int(weekly_xp) >= MIN_XP_TO_PROMOTE
    )
    in_relegate = (
        top_i > 0
        and size >= MIN_FOR_RELEGATION
        and my_league_rank > size - RELEGATE_BOTTOM
    )

    return {
        "period": period,
        "league": league_by_id(my_league_id),
        "all_leagues": LEAGUES,
        "my_rank": my_rank,
        "my_weekly_xp": int(weekly_xp),
        "my_period_xp": int(my_xp),
        "entries": entries,
        # Liga mexanikasi
        "league_rank": my_league_rank,
        "league_size": size,
        "promote_zone": in_promote,
        "relegate_zone": in_relegate,
        "promote_top": PROMOTE_TOP,
        "relegate_bottom": RELEGATE_BOTTOM,
        "min_xp_to_promote": MIN_XP_TO_PROMOTE,
        "next_league": (
            league_by_id(_shift(my_league_id, +1))
            if top_i < len(LEAGUE_ORDER) - 1
            else None
        ),
    }
