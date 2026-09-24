"""Oktagon mavsumi va haftalik reytingi (K25.3).

SOVRIN YO'Q — bu sof reyting: g'oliblar e'lon qilinadi va tarixda qoladi, VIP kunlari,
XP yoki streak muzlatkichi berilmaydi (foydalanuvchi qarori).

Ikki davr:

- **Haftalik Oktagon** — dushanba ~09:00 (Toshkent) o'tgan hafta yakunlanadi, top-3 e'lon
  qilinadi. Jadvalga BARCHA janglar kiradi (K25.4: sun'iy raqib o'quvchiga ko'rinmaydi —
  jadval undan farq qilsa, sezilib qoladi). Ball — o'sha haftada to'plangan SOF ball
  (`battles.p1_delta`/`p2_delta` yig'indisi, mag'lubiyatlar minus bilan).

- **Mavsum** — har oyning 1-sanasi ~09:00 o'tgan oy yakunlanadi: top-3 e'lon, keyin
  hamma o'yinchining Oktagon bali YUMSHOQ tiklanadi (yarmi qoladi) — ligalar qayta
  qiziqarli bo'ladi, lekin nolga tushib ketmaydi. `battle_games`/`battle_wins` (umrbod
  ko'rsatkichlar, nishonlar shularga bog'liq) TEGILMAYDI.

Markerlar: Meta «battle_week_done» / «battle_season_done» = yakunlangan davr kaliti.
Fon halqasi `loop(bot)` — main.py lifespan'da ro'yxatdan o'tadi.
"""

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import case, func, select

from db.models import Battle, BattleAward, Meta, User, utcnow
from services import battle as bt
from services.speaking_report import week_key, week_label, week_start_utc
from services.stats import TASHKENT_OFFSET

log = logging.getLogger(__name__)

CHECK_INTERVAL = 1200  # 20 daqiqa
ROLLOVER_HOUR = 9  # Toshkent; XP reytingi (09:00) yakunidan keyin
WEEK_MARKER = "battle_week_done"
SEASON_MARKER = "battle_season_done"

WEEK_TOP = 3
WEEK_MIN_PLAYERS = 3  # kamida shuncha jangchi bo'lsa g'oliblar e'lon qilinadi
SEASON_TOP = 3
SEASON_MIN_PLAYERS = 5
SEASON_KEEP = 0.5  # mavsum oxirida ball shu ulushi qoladi

ANNOUNCE_PAUSE = 0.05
RANK_ICON = {1: "🥇", 2: "🥈", 3: "🥉"}

UZ_MONTHS = [
    "yanvar", "fevral", "mart", "aprel", "may", "iyun",
    "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr",
]


def _local(now: datetime) -> datetime:
    return now + TASHKENT_OFFSET


# ───────────────────────── mavsum (oy) ─────────────────────────


def month_start_utc(now: datetime) -> datetime:
    """`now` tushgan oyning boshi — 1-sana 00:00 Toshkent, naive UTC."""
    local = _local(now).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return local - TASHKENT_OFFSET


def prev_month_start(month_start: datetime) -> datetime:
    local = _local(month_start) - timedelta(days=1)
    return local.replace(day=1, hour=0, minute=0, second=0, microsecond=0) - TASHKENT_OFFSET


def season_key(month_start: datetime) -> str:
    return _local(month_start).strftime("%Y-%m")


def season_label(month_start: datetime) -> str:
    local = _local(month_start)
    return f"{UZ_MONTHS[local.month - 1]} {local.year}"


def season_info(now: datetime | None = None) -> dict:
    """Joriy mavsum: kaliti, nomi, tugashigacha necha kun."""
    now = now or utcnow()
    start = month_start_utc(now)
    nxt = _local(start)
    nxt = (nxt.replace(day=28) + timedelta(days=7)).replace(day=1) - TASHKENT_OFFSET
    days = max(0, int((nxt - now).total_seconds() // 86400) + 1)
    return {
        "key": season_key(start),
        "label": season_label(start),
        "days_left": days,
        "ends_at": _local(nxt).strftime("%d.%m"),
        "keep_pct": int(SEASON_KEEP * 100),
    }


# ───────────────────────── haftalik jadval ─────────────────────────


async def week_board(session, since: datetime, until: datetime, limit: int = 50) -> list[dict]:
    """[since, until) oralig'idagi barcha janglar bo'yicha jadval. Ball — sof delta (mag'lubiyat minus)."""
    rows: dict[int, dict] = {}
    for id_col, delta_col, win_val in (
        (Battle.p1_id, Battle.p1_delta, 1),
        (Battle.p2_id, Battle.p2_delta, 2),
    ):
        res = (
            await session.execute(
                select(
                    id_col,
                    func.coalesce(func.sum(delta_col), 0),
                    func.count(Battle.id),
                    func.coalesce(func.sum(case((Battle.winner == win_val, 1), else_=0)), 0),
                )
                .where(Battle.created_at >= since, Battle.created_at < until)
                .group_by(id_col)
            )
        ).all()
        for uid, delta, games, wins in res:
            if uid is None:
                continue
            cur = rows.setdefault(uid, {"user_id": uid, "points": 0, "games": 0, "wins": 0})
            cur["points"] += int(delta or 0)
            cur["games"] += int(games or 0)
            cur["wins"] += int(wins or 0)
    if not rows:
        return []
    users = dict(
        (await session.execute(select(User.id, User.name).where(User.id.in_(list(rows)), User.is_demo == 0))).all()
    )
    out = [r | {"name": users.get(r["user_id"]) or "O'quvchi"} for r in rows.values() if r["user_id"] in users]
    out.sort(key=lambda r: (-r["points"], -r["wins"], r["games"], r["user_id"]))
    for i, r in enumerate(out, start=1):
        r["rank"] = i
    return out[:limit]


async def week_summary(session, user_id: int, now: datetime | None = None) -> dict:
    """Ilova uchun: joriy hafta jadvali + foydalanuvchining o'rni."""
    now = now or utcnow()
    start = week_start_utc(now)
    board = await week_board(session, start, start + timedelta(days=7), 20)
    mine = next((r for r in board if r["user_id"] == user_id), None)
    ends = start + timedelta(days=7)
    return {
        "label": week_label(start),
        "hours_left": max(0, int((ends - now).total_seconds() // 3600)),
        "top": board,
        "me": mine or {"rank": 0, "points": 0, "games": 0, "wins": 0},
        "min_players": WEEK_MIN_PLAYERS,
    }


async def past_awards(session, period: str, limit: int = 3) -> list[dict]:
    """Oxirgi yakunlangan davr g'oliblari."""
    key = (
        await session.execute(
            select(BattleAward.period_key)
            .where(BattleAward.period == period)
            .order_by(BattleAward.period_key.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if not key:
        return []
    rows = (
        await session.execute(
            select(BattleAward.rank, User.name, BattleAward.points, BattleAward.games, BattleAward.wins)
            .join(User, User.id == BattleAward.user_id)
            .where(BattleAward.period == period, BattleAward.period_key == key)
            .order_by(BattleAward.rank)
            .limit(limit)
        )
    ).all()
    return [
        {"rank": r, "name": n or "O'quvchi", "points": p, "games": g, "wins": w, "period_key": key}
        for r, n, p, g, w in rows
    ]


# ───────────────────────── davr yakuni ─────────────────────────


async def _marker_done(session, key: str, value: str) -> bool:
    marker = (await session.execute(select(Meta).where(Meta.key == key))).scalar_one_or_none()
    return bool(marker and marker.value == value)


async def _mark(session, key: str, value: str) -> None:
    marker = (await session.execute(select(Meta).where(Meta.key == key))).scalar_one_or_none()
    if marker:
        marker.value = value
    else:
        marker = Meta(key=key, value=value)
    session.add(marker)
    await session.commit()


async def _record(session, period: str, period_key: str, board: list[dict], top_n: int) -> list[dict]:
    """Top-n ni `battle_awards` ga yozadi (faqat tarix — sovrin yo'q). Qaytaradi: g'oliblar."""
    winners: list[dict] = []
    for row in board[:top_n]:
        rank = row["rank"]
        exists = (
            await session.execute(
                select(BattleAward.id).where(
                    BattleAward.user_id == row["user_id"],
                    BattleAward.period == period,
                    BattleAward.period_key == period_key,
                )
            )
        ).scalar_one_or_none()
        if exists:
            continue
        user = await session.get(User, row["user_id"])
        if user is None:
            continue
        session.add(
            BattleAward(
                user_id=user.id,
                period=period,
                period_key=period_key,
                rank=rank,
                points=row["points"],
                games=row["games"],
                wins=row["wins"],
            )
        )
        winners.append(row | {"tg_id": user.tg_id})
    await session.commit()
    return winners


def winners_text(period: str, label: str, winners: list[dict], me: dict | None, total: int) -> str:
    head = "⚔️ <b>Haftalik Oktagon yakunlandi</b>" if period == "week" else "🏆 <b>Oktagon mavsumi yakunlandi</b>"
    lines = [f"{head} · {label}", ""]
    for w in winners:
        lines.append(
            f"{RANK_ICON.get(w['rank'], '🏅')} <b>{w['name']}</b> — {w['points']} ball "
            f"({w['wins']}/{w['games']} g'alaba)"
        )
    lines.append("")
    if me and me.get("rank"):
        lines.append(f"Siz: <b>{me['rank']}-o'rin</b>, {me['points']} ball ({total} jangchi).")
    if period == "season":
        lines.append(
            f"Yangi mavsum boshlandi — ballarning {int(SEASON_KEEP * 100)}% i qoldi, "
            "ligalar qaytadan jangga chaqiryapti."
        )
    else:
        lines.append("Yangi hafta boshlandi — Oktagonda 1-o'rin sizniki bo'lishi mumkin ⚔️")
    return "\n".join(lines)


def _battle_kb():
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

    from services.deploy_notify import webapp_url_versioned

    url = webapp_url_versioned()
    if not url.startswith("https://"):
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⚔️ Oktagonga kirish", web_app=WebAppInfo(url=url + "#battle"))]]
    )


async def announce(bot, period: str, label: str, winners: list[dict], board: list[dict]) -> dict:
    """Davr ishtirokchilariga e'lon (hammaga emas — faqat jang qilganlarga)."""
    out = {"sent": 0, "failed": 0}
    if not winners:
        return out
    kb = _battle_kb()
    async with bt.sessions() as session:
        tg = dict(
            (
                await session.execute(
                    select(User.id, User.tg_id).where(User.id.in_([r["user_id"] for r in board]), User.tg_id > 0)
                )
            ).all()
        )
    for row in board:
        chat = tg.get(row["user_id"])
        if not chat:
            continue
        try:
            await bot.send_message(
                chat, winners_text(period, label, winners, row, len(board)), parse_mode="HTML", reply_markup=kb
            )
            out["sent"] += 1
        except Exception:
            out["failed"] += 1
        await asyncio.sleep(ANNOUNCE_PAUSE)
    return out


async def run_week(bot, now: datetime | None = None) -> dict | None:
    """O'tgan hafta yakuni — hafta uchun bir marta. Yakunlansa natija, aks holda None."""
    now = now or utcnow()
    start = week_start_utc(now) - timedelta(days=7)
    key, label = week_key(start), week_label(start)
    async with bt.sessions() as session:
        if await _marker_done(session, WEEK_MARKER, key):
            return None
        board = await week_board(session, start, start + timedelta(days=7), 50)
        winners = await _record(session, "week", key, board, WEEK_TOP) if len(board) >= WEEK_MIN_PLAYERS else []
        await _mark(session, WEEK_MARKER, key)
    if bot and winners:
        await announce(bot, "week", label, winners, board)
    return {"key": key, "label": label, "players": len(board), "winners": winners}


async def run_season(bot, now: datetime | None = None) -> dict | None:
    """O'tgan mavsum yakuni + yumshoq tiklash — mavsum uchun bir marta."""
    now = now or utcnow()
    start = prev_month_start(month_start_utc(now))
    key, label = season_key(start), season_label(start)
    async with bt.sessions() as session:
        if await _marker_done(session, SEASON_MARKER, key):
            return None
        board = [
            {"user_id": r["user_id"], "name": r["name"], "points": r["points"], "games": r["games"], "wins": r["wins"], "rank": r["rank"]}
            for r in await bt.top(session, 50)
        ]
        winners = await _record(session, "season", key, board, SEASON_TOP) if len(board) >= SEASON_MIN_PLAYERS else []
        # Yumshoq tiklash — hamma o'yinchiga (janglar/g'alabalar tegilmaydi)
        reset = 0
        if winners or len(board) >= SEASON_MIN_PLAYERS:
            users = (await session.execute(select(User).where(User.battle_points > 0))).scalars().all()
            for u in users:
                u.battle_points = int((u.battle_points or 0) * SEASON_KEEP)
                session.add(u)
            reset = len(users)
            await session.commit()
        await _mark(session, SEASON_MARKER, key)
    if bot and winners:
        await announce(bot, "season", label, winners, board)
    return {"key": key, "label": label, "players": len(board), "winners": winners, "reset": reset}


async def loop(bot) -> None:
    """Fon halqasi: dushanba va oy boshida yakun."""
    while True:
        try:
            local = _local(utcnow())
            if local.weekday() == 0 and local.hour >= ROLLOVER_HOUR:
                await run_week(bot)
            if local.day == 1 and local.hour >= ROLLOVER_HOUR:
                await run_season(bot)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("Oktagon mavsumi xatosi: %r", e)
        await asyncio.sleep(CHECK_INTERVAL)


__all__ = [
    "SEASON_KEEP",
    "announce",
    "loop",
    "month_start_utc",
    "past_awards",
    "prev_month_start",
    "run_season",
    "run_week",
    "season_info",
    "season_key",
    "season_label",
    "week_board",
    "week_summary",
    "winners_text",
]
