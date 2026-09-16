"""Haftalik speaking hisoboti (K18.4) — dushanba ertalab o'tgan hafta yakuni.

Speaking faolligi bo'lgan har foydalanuvchiga Telegram'da qisqa hisobot:
suhbat javoblari (ovozli ulushi, xatosiz %), mock (eng yaxshisi), kunlik savol
(kunlar, o'rtacha, streak), talaffuz va tinglash mashqlari, daftardagi yangi
xatolar, speaking XP; o'tgan haftaga nisbatan ▲/▼ va bitta amaliy maslahat.
O'tgan hafta jim qolganlarga (undan oldingi hafta faol bo'lgan) — qisqa turtki.

Halqa (`report_loop`, 20 daqiqa): dushanba 10–21 Toshkent oralig'ida `process()`;
har foydalanuvchiga bir hafta uchun bir marta (`users.speak_report_key` =
o'tgan dushanba sanasi) — qayta ishga tushsa ham takrorlanmaydi.
`/hisobot` buyrug'i xuddi shu matnni joriy hafta (dushanbadan hozirgacha) uchun
beradi — dushanbani kutmasdan ko'rish uchun.
"""

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.models import (
    DailySpeaking,
    DrillResult,
    ListeningResult,
    MockResult,
    TutorMistake,
    TutorTurn,
    User,
    XpLog,
    utcnow,
)
from services import billing, daily
from services.stats import TASHKENT_OFFSET

log = logging.getLogger(__name__)

CHECK_INTERVAL = 1200  # 20 daqiqa
REPORT_HOUR_FROM, REPORT_HOUR_TO = 10, 21  # dushanba, Toshkent soati (09:00 da reyting yakuni)
SEND_PAUSE = 0.05  # Telegram limiti (~30 xabar/soniya) uchun tanaffus
XP_SOURCES = ("tutor:%", "drill:%", "listen:%", "daily:%")
EMPTY = {
    "chat": 0, "chat_voice": 0, "chat_ok": 0,
    "mock_n": 0, "mock_avg": 0, "mock_best": 0, "mock_best_title": "",
    "daily_days": 0, "daily_avg": 0, "daily_voice": 0,
    "drill_n": 0, "drill_sent": 0, "drill_avg": 0,
    "listen_n": 0, "listen_avg": 0,
    "mistakes_new": 0, "xp": 0, "total": 0,
}


def _local(now: datetime) -> datetime:
    return now + TASHKENT_OFFSET


def week_start_utc(now: datetime) -> datetime:
    """`now` (naive UTC) tushgan haftaning boshi — dushanba 00:00 Toshkent, naive UTC."""
    local = _local(now)
    monday = (local - timedelta(days=local.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return monday - TASHKENT_OFFSET


def week_key(week_start: datetime) -> str:
    return _local(week_start).strftime("%Y-%m-%d")


def week_label(week_start: datetime, until: datetime | None = None) -> str:
    """'08.09 — 14.09.2026' (until berilsa — shu kungacha, joriy hafta uchun)."""
    a = _local(week_start)
    b = _local(until) if until else a + timedelta(days=6)
    return f"{a:%d.%m} — {b:%d.%m.%Y}"


def _pct(part: int, whole: int) -> int:
    return round(part * 100 / whole) if whole else 0


async def stats(session: AsyncSession, user_id: int, since: datetime, until: datetime) -> dict:
    """[since, until) oralig'idagi speaking faolligi (naive UTC chegaralar)."""
    from services import tutor

    s = dict(EMPTY)
    rows = (
        await session.execute(
            select(TutorTurn.voice, TutorTurn.ok).where(
                TutorTurn.user_id == user_id, TutorTurn.mode == "chat",
                TutorTurn.created_at >= since, TutorTurn.created_at < until,
            )
        )
    ).all()
    s["chat"] = len(rows)
    s["chat_voice"] = sum(1 for v, _ in rows if v)
    s["chat_ok"] = sum(1 for _, ok in rows if ok)

    mocks = (
        await session.execute(
            select(MockResult.mock_id, MockResult.score).where(
                MockResult.user_id == user_id,
                MockResult.created_at >= since, MockResult.created_at < until,
            )
        )
    ).all()
    if mocks:
        s["mock_n"] = len(mocks)
        s["mock_avg"] = round(sum(sc for _, sc in mocks) / len(mocks))
        best_id, best = max(mocks, key=lambda r: r[1])
        s["mock_best"] = best
        s["mock_best_title"] = (tutor.MOCK_BY_ID.get(best_id) or {}).get("title_uz", best_id)

    # Kunlik savol Toshkent sanasi bilan saqlanadi; `until` kun o'rtasida bo'lsa
    # (joriy hafta) o'sha kun ham kiradi, yarim tunda (hafta chegarasi) — kirmaydi
    day_from = _local(since).date().isoformat()
    day_to = (_local(until) - timedelta(microseconds=1)).date().isoformat()
    days = (
        await session.execute(
            select(DailySpeaking.score, DailySpeaking.voice).where(
                DailySpeaking.user_id == user_id,
                DailySpeaking.day >= day_from, DailySpeaking.day <= day_to,
            )
        )
    ).all()
    if days:
        s["daily_days"] = len(days)
        s["daily_avg"] = round(sum(sc for sc, _ in days) / len(days))
        s["daily_voice"] = sum(1 for _, v in days if v)

    drills = (
        await session.execute(
            select(DrillResult.score, DrillResult.count).where(
                DrillResult.user_id == user_id,
                DrillResult.created_at >= since, DrillResult.created_at < until,
            )
        )
    ).all()
    if drills:
        s["drill_n"] = len(drills)
        s["drill_sent"] = sum(c for _, c in drills)
        s["drill_avg"] = round(sum(sc for sc, _ in drills) / len(drills))

    listens = (
        await session.execute(
            select(ListeningResult.score).where(
                ListeningResult.user_id == user_id,
                ListeningResult.created_at >= since, ListeningResult.created_at < until,
            )
        )
    ).scalars().all()
    if listens:
        s["listen_n"] = len(listens)
        s["listen_avg"] = round(sum(listens) / len(listens))

    s["mistakes_new"] = (
        await session.execute(
            select(func.count()).select_from(TutorMistake).where(
                TutorMistake.user_id == user_id,
                TutorMistake.created_at >= since, TutorMistake.created_at < until,
            )
        )
    ).scalar_one()
    s["xp"] = (
        await session.execute(
            select(func.coalesce(func.sum(XpLog.amount), 0)).where(
                XpLog.user_id == user_id,
                XpLog.created_at >= since, XpLog.created_at < until,
                or_(*[XpLog.source.like(p) for p in XP_SOURCES]),
            )
        )
    ).scalar_one()
    s["total"] = s["chat"] + s["mock_n"] + s["daily_days"] + s["drill_n"] + s["listen_n"]
    return s


async def context(session: AsyncSession, user: User, now: datetime) -> dict:
    """Oynadan tashqari holat: daftardagi ochiq xatolar, kunlik savol streak'i, VIP."""
    open_n = (
        await session.execute(
            select(func.count()).select_from(TutorMistake).where(TutorMistake.user_id == user.id)
        )
    ).scalar_one()
    streak, _best = daily.streak_of(await daily.history(session, user.id), _local(now).date())
    return {"mistakes_open": open_n, "streak": streak, "vip": billing.is_vip(user)}


def _delta(cur: int, prev: int) -> str:
    if not prev or cur == prev:
        return ""
    return f" ▲ {cur - prev}" if cur > prev else f" ▼ {prev - cur}"


def tip(cur: dict, ctx: dict, current_week: bool = False, days_left: int = 0) -> str:
    """Bitta amaliy maslahat — eng foydali bo'shliq bo'yicha."""
    if cur["daily_days"] == 0:
        return (
            "🎙 Kunlik savol bepul — har kuni 1 daqiqa, +5 XP va streak 🔥. "
            "Bosh sahifadagi kartadan boshlang."
        )
    if ctx["mistakes_open"] >= 3:
        return (
            f"📒 Daftarda {ctx['mistakes_open']} ta jumla kutmoqda — eshitib, qayta ayting: "
            "shunda xato qaytmaydi."
        )
    if cur["daily_days"] < 7 and not current_week:
        return (
            f"🎙 Kunlik savolni {7 - cur['daily_days']} kun o'tkazib yubordingiz — "
            "har kuni javob bersangiz streak 🔥 tez o'sadi."
        )
    if cur["chat"] and cur["chat_voice"] * 2 < cur["chat"]:
        return "🎤 Ko'proq ovoz bilan gapiring — talaffuz bali faqat ovozli javobda hisoblanadi."
    if cur["mock_n"] == 0 and ctx["vip"]:
        return "🎯 Mock imtihon topshiring — 5 savol, 70%+ bo'lsa sertifikat beriladi."
    if cur["drill_n"] == 0 and cur["listen_n"] == 0:
        return "🎤 Talaffuz va 🎧 tinglash bo'limlari bepul — mavzu tanlab 10 jumla mashq qiling."
    if current_week and days_left > 0:
        return f"Zo'r sur'at — haftaning qolgan {days_left} kunida ham shu ruhda davom eting 💪"
    return "Zo'r sur'at — shu ruhda davom eting! Til — mushak: har kuni ozgina 💪"


def render(
    user: User, cur: dict, prev: dict, label: str, ctx: dict, *, current_week: bool = False, days_left: int = 0
) -> str:
    """Hisobot matni (HTML). `days_left` — joriy haftada qolgan kunlar (faqat /hisobot)."""
    name = user.name or "do'stim"
    head = "🗣 <b>Speaking — joriy hafta</b>" if current_week else "🗣 <b>Haftalik speaking hisoboti</b>"
    lines = [head, f"📅 {label}", ""]

    if cur["total"] == 0:
        if current_week:
            lines.append(
                f"{name}, bu hafta hali speaking mashqi yo'q. "
                "AI ustoz bilan 5 daqiqa suhbat yoki 🎙 kunlik savol — hoziroq boshlang 👇"
            )
        else:
            was = f"O'tgan hafta {prev['total']} ta mashq qilgan edingiz. " if prev["total"] else ""
            lines.append(
                f"{name}, bu hafta speaking mashqi bo'lmadi 😔 {was}"
                "Til — mushak: haftada 3 marta 5 daqiqa ham yetadi. Bugun boshlang 👇"
            )
        return "\n".join(lines)

    if cur["chat"]:
        lines.append(
            f"💬 Suhbat: <b>{cur['chat']}</b> javob{_delta(cur['chat'], prev['chat'])}"
            f" · 🎤 {cur['chat_voice']} ovozli · xatosiz {_pct(cur['chat_ok'], cur['chat'])}%"
        )
    if cur["mock_n"]:
        lines.append(
            f"🎯 Mock: {cur['mock_n']} imtihon · eng yaxshi <b>{cur['mock_best_title']} "
            f"{cur['mock_best']}%</b>{_delta(cur['mock_best'], prev['mock_best'])}"
        )
    if cur["daily_days"]:
        streak = f" · 🔥 streak {ctx['streak']}" if ctx["streak"] > 1 else ""
        lines.append(
            f"🎙 Kunlik savol: <b>{cur['daily_days']}/7</b> kun · o'rtacha {cur['daily_avg']}%"
            f"{_delta(cur['daily_avg'], prev['daily_avg'])}{streak}"
        )
    if cur["drill_n"]:
        lines.append(
            f"🎤 Talaffuz: {cur['drill_n']} mashq · {cur['drill_sent']} jumla · "
            f"o'rtacha {cur['drill_avg']}%{_delta(cur['drill_avg'], prev['drill_avg'])}"
        )
    if cur["listen_n"]:
        lines.append(
            f"🎧 Tinglash: {cur['listen_n']} mashq · o'rtacha {cur['listen_avg']}%"
            f"{_delta(cur['listen_avg'], prev['listen_avg'])}"
        )
    if cur["mistakes_new"] or ctx["mistakes_open"]:
        lines.append(
            f"📒 Daftar: +{cur['mistakes_new']} yangi xato · jami {ctx['mistakes_open']} ta kutmoqda"
        )

    prev_xp = f" (o'tgan hafta {prev['xp']}{_delta(cur['xp'], prev['xp'])})" if prev["xp"] else ""
    lines += ["", f"⭐ Speaking XP: <b>{cur['xp']}</b>{prev_xp}", "", f"💡 {tip(cur, ctx, current_week, days_left)}"]
    return "\n".join(lines)


def open_kb(text: str = "🤖 AI ustozni ochish"):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

    from services.deploy_notify import webapp_url_versioned

    url = webapp_url_versioned()
    if not url.startswith("https://"):
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=text, web_app=WebAppInfo(url=url + "#tutor"))]]
    )


async def weekly_text(session: AsyncSession, user: User, week_start: datetime, now: datetime) -> str:
    """O'tgan (yakunlangan) hafta hisoboti — dushanba xabari."""
    end = week_start + timedelta(days=7)
    cur = await stats(session, user.id, week_start, end)
    prev = await stats(session, user.id, week_start - timedelta(days=7), week_start)
    return render(user, cur, prev, week_label(week_start), await context(session, user, now))


async def current_text(session: AsyncSession, user: User, now: datetime | None = None) -> str:
    """Joriy hafta (dushanbadan hozirgacha) — /hisobot buyrug'i."""
    now = now or utcnow()
    start = week_start_utc(now)
    cur = await stats(session, user.id, start, now)
    prev = await stats(session, user.id, start - timedelta(days=7), start)
    days_left = 6 - (_local(now).date() - _local(start).date()).days  # bugundan tashqari
    return render(
        user, cur, prev, week_label(start, now), await context(session, user, now),
        current_week=True, days_left=days_left,
    )


async def _active_user_ids(session: AsyncSession, since: datetime) -> set[int]:
    """`since` dan beri biror speaking jadvalida izi bor foydalanuvchilar."""
    ids: set[int] = set()
    for model in (TutorTurn, MockResult, DrillResult, ListeningResult):
        rows = (
            await session.execute(
                select(model.user_id).where(model.created_at >= since).distinct()
            )
        ).scalars().all()
        ids.update(rows)
    rows = (
        await session.execute(
            select(DailySpeaking.user_id)
            .where(DailySpeaking.day >= _local(since).date().isoformat())
            .distinct()
        )
    ).scalars().all()
    ids.update(rows)
    return ids


def _due(now: datetime) -> bool:
    local = _local(now)
    return local.weekday() == 0 and REPORT_HOUR_FROM <= local.hour < REPORT_HOUR_TO


async def process(session: AsyncSession, bot, now: datetime | None = None) -> dict:
    """Bir aylanish: dushanba kunduzi o'tgan hafta hisobotlarini tarqatadi.

    Qaytaradi: {"sent": hisobot, "nudged": turtki, "failed": yetmagan}.
    """
    now = now or utcnow()
    out = {"sent": 0, "nudged": 0, "failed": 0}
    if not _due(now):
        return out

    this_monday = week_start_utc(now)
    prev_monday = this_monday - timedelta(days=7)
    key = week_key(prev_monday)
    # O'tgan 2 haftada faol bo'lganlar (jim qolganlarga bir marta turtki)
    ids = await _active_user_ids(session, prev_monday - timedelta(days=7))
    if not ids:
        return out
    users = (
        await session.execute(
            select(User).where(
                User.id.in_(ids), User.is_demo == 0, User.tg_id > 0,
                User.speak_report_key != key,
            )
        )
    ).scalars().all()

    kb = open_kb()
    for user in users:
        user.speak_report_key = key  # yetmasa ham qayta urinmaymiz
        cur = await stats(session, user.id, prev_monday, this_monday)
        prev = await stats(session, user.id, prev_monday - timedelta(days=7), prev_monday)
        if cur["total"] == 0 and prev["total"] == 0:
            continue
        text = render(user, cur, prev, week_label(prev_monday), await context(session, user, now))
        try:
            await bot.send_message(user.tg_id, text, parse_mode="HTML", reply_markup=kb)
            out["sent" if cur["total"] else "nudged"] += 1
        except Exception as e:  # bloklagan bo'lishi mumkin
            out["failed"] += 1
            log.info("speaking hisoboti yetmadi (%s): %r", user.tg_id, e)
        await session.commit()
        await asyncio.sleep(SEND_PAUSE)

    if settings.admin_id and (out["sent"] or out["nudged"]):
        try:
            await bot.send_message(
                settings.admin_id,
                f"🗣 Haftalik speaking hisoboti ({week_label(prev_monday)}): "
                f"{out['sent']} ta hisobot, {out['nudged']} ta turtki, {out['failed']} ta yetmadi.",
            )
        except Exception as e:
            log.warning("admin hisobot xabari yuborilmadi: %r", e)
    return out


async def report_loop(bot) -> None:
    """Fon halqasi — dushanba kunduzi hisobotlarni tarqatadi (20 daqiqada bir tekshiradi)."""
    from db.session import SessionLocal

    while True:
        try:
            if _due(utcnow()):
                async with SessionLocal() as session:
                    await process(session, bot)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("Speaking hisoboti xatosi: %r", e)
        await asyncio.sleep(CHECK_INTERVAL)
