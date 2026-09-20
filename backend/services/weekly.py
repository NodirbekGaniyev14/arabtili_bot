"""Reyting yakuni: haftalik (dushanba, top-3) + oylik (1-sana, top-5).

FastAPI lifespan'da fon vazifasi sifatida ishlaydi:
- har dushanba ~09:00 (Toshkent) o'tgan hafta yakunlanadi — top-3 ga sovrin;
- har oy 1-sanasi ~09:00 o'tgan oy yakunlanadi — top-5 ga sovrin;
- har 20 daqiqada o'rinlar qayta hisoblanadi; kimdir tushib ketgan bo'lsa
  unga xabar yuboriladi (bir foydalanuvchiga 6 soatda bir martadan ko'p emas).

Ligalar — faqat XP yorlig'i (ko'tarilish/tushish yo'q); hamma bitta
umumiy reytingda bellashadi.
"""

import asyncio
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from sqlalchemy import select

from db.models import Meta, Plan, User, WeeklyAward, XpLog
from db.session import SessionLocal
from services.certificate import issue_rank_certificate
from services.league import (
    _month_start_utc,
    _ranked_rows,
    _week_start_utc,
    refresh_ranks,
    top_winners,
)
from services.stats import TASHKENT_OFFSET

# G'oliblar e'loni: davr yakunida HAMMAGA (rejasi bor, 90 kun ichida faol) bitta xabar —
# top-3/5, sovrin va o'zining o'rni. Bloklaganlar/o'lik hisoblar chetlab o'tiladi.
ANNOUNCE_ACTIVE_DAYS = 90
ANNOUNCE_PAUSE = 0.05

ROLLOVER_HOUR = 9  # Toshkent vaqti (ham haftalik, ham oylik)
CHECK_INTERVAL = 1200  # 20 daqiqa
NOTICE_COOLDOWN_HOURS = 6
NOTICE_TOP_N = 10  # faqat yuqori o'rinlar uchun xabar beramiz
ROLLOVER_KEY = "weekly_rollover_done"
MONTHLY_KEY = "monthly_rollover_done"

WEEKLY_TOP = 3
WEEKLY_MIN = 3
MONTHLY_TOP = 5
MONTHLY_MIN = 5  # oylik sovrin uchun kamida 5 ishtirokchi

RANK_ICON = {1: "🥇", 2: "🥈", 3: "🥉", 4: "🎗", 5: "🎗"}
# Sovrin: VIP kunlari (AI ustoz) — o'rin bo'yicha; + 1 streak muzlatkichi (ko'pi bilan 2).
# Bizga xarajati deyarli nol, motivatsiya kuchli; VIP faol bo'lsa muddat oxiriga qo'shiladi.
VIP_PRIZE = {"week": {1: 7, 2: 3, 3: 3}, "month": {1: 14, 2: 7, 3: 7, 4: 3, 5: 3}}


def prize_days(period: str, rank: int) -> int:
    return VIP_PRIZE.get(period, {}).get(rank, 0)


def prize_text(period: str, rank: int) -> str:
    days = prize_days(period, rank)
    if not days:
        return ""
    return f"\n\n🎁 Sovrin: <b>{days} kun VIP</b> (AI ustoz, mock, speaking) + 🧊 streak muzlatkichi."


UZ_MONTHS = [
    "yanvar", "fevral", "mart", "aprel", "may", "iyun",
    "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr",
]


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _local_now() -> datetime:
    return _now() + TASHKENT_OFFSET


def _week_label(week_start: datetime) -> str:
    """'14.07 — 20.07.2026' ko'rinishidagi hafta yorlig'i (Toshkent)."""
    start_local = week_start + TASHKENT_OFFSET
    end_local = start_local + timedelta(days=6)
    return f"{start_local.strftime('%d.%m')} — {end_local.strftime('%d.%m.%Y')}"


def _prev_month_start(month_start: datetime) -> datetime:
    """Berilgan oy boshidan oldingi oyning boshi (naive UTC)."""
    local = month_start + TASHKENT_OFFSET
    prev_last = local - timedelta(days=1)  # o'tgan oyning oxirgi kuni
    prev_first = prev_last.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return prev_first - TASHKENT_OFFSET


def _month_label(month_start: datetime) -> str:
    """'iyul 2026' ko'rinishidagi oy yorlig'i (Toshkent)."""
    local = month_start + TASHKENT_OFFSET
    return f"{UZ_MONTHS[local.month - 1]} {local.year}"


def _month_key(month_start: datetime) -> str:
    """'2026-07' — oylik davr kaliti (haftalik 'YYYY-MM-DD' bilan to'qnashmaydi)."""
    return (month_start + TASHKENT_OFFSET).strftime("%Y-%m")


async def _award_period(
    bot: Bot,
    *,
    marker_key: str,
    period: str,
    period_key: str,
    label: str,
    since: datetime,
    top_n: int,
    min_participants: int,
    caption_word: str,
) -> list | None:
    """Bitta davr (hafta/oy) g'oliblariga sovrin beradi — davr uchun bir marta.
    Qaytaradi: g'oliblar ro'yxati (yangi yakunlangan bo'lsa), aks holda None."""
    async with SessionLocal() as session:
        marker = (
            await session.execute(select(Meta).where(Meta.key == marker_key))
        ).scalar_one_or_none()
        if marker and marker.value == period_key:
            return None  # bu davr allaqachon yakunlangan

        winners = await top_winners(session, since, top_n, min_participants)

        for user_id, name, xp, rank in winners:
            exists = (
                await session.execute(
                    select(WeeklyAward).where(
                        WeeklyAward.user_id == user_id,
                        WeeklyAward.week_start == period_key,
                    )
                )
            ).scalar_one_or_none()
            if exists:
                continue

            user = (
                await session.execute(select(User).where(User.id == user_id))
            ).scalar_one_or_none()
            if user is None:
                continue

            try:
                cert = await issue_rank_certificate(
                    session, user_id, user.name or name, rank, xp, label, period=period
                )
            except Exception as e:
                print(f"{period} sertifikat xatosi (user={user_id}): {e!r}")
                continue

            # Sovrin: VIP kunlari + streak muzlatkichi
            days = prize_days(period, rank)
            if days:
                from services import billing
                from services.stats import MAX_FREEZES

                billing.grant(user, days)
                user.streak_freezes = min((user.streak_freezes or 0) + 1, MAX_FREEZES)
                session.add(user)
            session.add(
                WeeklyAward(
                    user_id=user_id,
                    week_start=period_key,
                    period=period,
                    rank=rank,
                    weekly_xp=xp,
                    cert_id=cert.cert_id,
                    vip_days=days,
                )
            )
            await session.commit()

            try:
                from aiogram.types import FSInputFile

                await bot.send_photo(
                    user.tg_id,
                    FSInputFile(cert.png_path),
                    caption=(
                        f"{RANK_ICON.get(rank, '🏅')} <b>{caption_word} reyting: "
                        f"{rank}-o'rin!</b>\n\n"
                        f"{label} davrida {xp} XP to'pladingiz. "
                        f"Sovrin sertifikatingiz tayyor — tabriklaymiz!"
                        f"{prize_text(period, rank)}"
                    ),
                    parse_mode="HTML",
                )
            except Exception:
                pass

        # Yakunlangan deb belgilaymiz (g'olib bo'lmasa ham — takror urinmaslik uchun)
        if marker:
            marker.value = period_key
        else:
            marker = Meta(key=marker_key, value=period_key)
        session.add(marker)
        await session.commit()
        return winners


def _rating_kb():
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

    from services.deploy_notify import webapp_url_versioned

    url = webapp_url_versioned()
    if not url.startswith("https://"):
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🏆 Reytingni ochish", web_app=WebAppInfo(url=url + "#rating"))]]
    )


def announcement_text(period: str, label: str, winners: list, my: tuple | None, participants: int) -> str:
    """Hamma uchun e'lon: g'oliblar + sovrin + o'quvchining o'z o'rni."""
    head = "🏆 <b>Haftalik reyting yakunlandi</b>" if period == "week" else "🏆 <b>Oylik reyting yakunlandi</b>"
    lines = [f"{head} · {label}", ""]
    for _uid, name, xp, rank in winners:
        prize = prize_days(period, rank)
        lines.append(f"{RANK_ICON.get(rank, '🏅')} <b>{name}</b> — {xp} XP" + (f" · 🎁 {prize} kun VIP" if prize else ""))
    lines.append("")
    if my:
        rank, xp = my
        if rank <= len(winners):
            lines.append(f"Siz {rank}-o'rindasiz — tabriklaymiz! 🎉")
        else:
            lines.append(f"Siz: <b>{rank}-o'rin</b>, {xp} XP ({participants} ishtirokchi).")
    else:
        lines.append(f"Bu davrda {participants} kishi qatnashdi — siz hali yo'q edingiz.")
    nxt = "Yangi hafta boshlandi" if period == "week" else "Yangi oy boshlandi"
    top = "top-3" if period == "week" else "top-5"
    lines.append(f"{nxt} — bugun 1 dars, va {top} sizniki bo'lishi mumkin: sovrin VIP kunlar + sertifikat 🚀")
    return "\n".join(lines)


async def announce_winners(bot: Bot, period: str, label: str, winners: list, since: datetime) -> dict:
    """Davr yakunini hammaga e'lon qiladi (rejasi bor, 90 kun ichida faol). {"sent", "failed"}."""
    out = {"sent": 0, "failed": 0}
    if not winners:
        return out
    async with SessionLocal() as session:
        ranked = await _ranked_rows(session, since)
        real = [r for r in ranked if not r.is_demo and r.xp > 0]
        my_pos = {r.id: (pos, int(r.xp)) for pos, r in enumerate(real, start=1)}
        active_since = _now() - timedelta(days=ANNOUNCE_ACTIVE_DAYS)
        active_ids = set(
            (await session.execute(select(XpLog.user_id).where(XpLog.created_at >= active_since).distinct())).scalars().all()
        )
        plan_ids = set((await session.execute(select(Plan.user_id).distinct())).scalars().all())
        users = (
            await session.execute(select(User).where(User.is_demo == 0, User.tg_id > 0))
        ).scalars().all()
    kb = _rating_kb()
    for user in users:
        if user.id not in plan_ids or user.id not in active_ids:
            continue
        text = announcement_text(period, label, winners, my_pos.get(user.id), len(real))
        try:
            await bot.send_message(user.tg_id, text, parse_mode="HTML", reply_markup=kb)
            out["sent"] += 1
        except Exception:
            out["failed"] += 1
        await asyncio.sleep(ANNOUNCE_PAUSE)
    return out


async def _rollover(bot: Bot) -> None:
    """Haftalik yakun — o'tgan hafta top-3, keyin hammaga e'lon."""
    prev = _week_start_utc() - timedelta(days=7)
    winners = await _award_period(
        bot,
        marker_key=ROLLOVER_KEY,
        period="week",
        period_key=(prev + TASHKENT_OFFSET).strftime("%Y-%m-%d"),
        label=_week_label(prev),
        since=prev,
        top_n=WEEKLY_TOP,
        min_participants=WEEKLY_MIN,
        caption_word="Haftalik",
    )
    if winners:
        await announce_winners(bot, "week", _week_label(prev), winners, prev)


async def _monthly_rollover(bot: Bot) -> None:
    """Oylik yakun — o'tgan oy top-5, keyin hammaga e'lon."""
    prev = _prev_month_start(_month_start_utc())
    winners = await _award_period(
        bot,
        marker_key=MONTHLY_KEY,
        period="month",
        period_key=_month_key(prev),
        label=_month_label(prev),
        since=prev,
        top_n=MONTHLY_TOP,
        min_participants=MONTHLY_MIN,
        caption_word="Oylik",
    )
    if winners:
        await announce_winners(bot, "month", _month_label(prev), winners, prev)


async def _notify_rank_drops(bot: Bot) -> None:
    """O'rni tushganlarga xabar (throttling bilan)."""
    async with SessionLocal() as session:
        dropped = await refresh_ranks(session)
        if not dropped:
            return

        now = _now()
        for user, old_rank, new_rank in dropped:
            if new_rank > NOTICE_TOP_N:
                continue  # pastki o'rinlar uchun bezovta qilmaymiz
            if user.rank_notice_at and (now - user.rank_notice_at) < timedelta(
                hours=NOTICE_COOLDOWN_HOURS
            ):
                continue
            if user.tg_id <= 0:
                continue

            try:
                await bot.send_message(
                    user.tg_id,
                    f"📉 <b>{old_rank}-o'rin boy berildi!</b>\n\n"
                    f"Hozir siz {new_rank}-o'rindasiz. Bir-ikki dars bajarib "
                    f"XP to'plang va o'rningizni qaytarib oling 💪",
                    parse_mode="HTML",
                )
                user.rank_notice_at = now
                session.add(user)
            except Exception:
                pass

        await session.commit()


async def weekly_loop(bot: Bot) -> None:
    """Fon halqasi — hafta yakuni va o'rin kuzatuvi."""
    while True:
        try:
            local = _local_now()
            if local.weekday() == 0 and local.hour >= ROLLOVER_HOUR:
                await _rollover(bot)
                # Admin haftalik digest (K20.3) — reyting yakunidan keyin, bir marta
                from services import admin_digest

                await admin_digest.maybe_send(bot)
            if local.day == 1 and local.hour >= ROLLOVER_HOUR:
                await _monthly_rollover(bot)
            await _notify_rank_drops(bot)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"Haftalik reyting xatosi: {e!r}")
        await asyncio.sleep(CHECK_INTERVAL)
