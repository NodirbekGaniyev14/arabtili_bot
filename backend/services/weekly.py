"""Haftalik reyting: dushanba yakuni (top-3 sertifikati) + o'rin kuzatuvi.

FastAPI lifespan'da fon vazifasi sifatida ishlaydi:
- har dushanba Toshkent vaqti bilan ~09:00 da o'tgan hafta yakunlanadi va
  g'oliblarga sertifikat yuboriladi (bir hafta uchun bir marta);
- har 20 daqiqada o'rinlar qayta hisoblanadi; kimdir tushib ketgan bo'lsa
  unga xabar yuboriladi (bir foydalanuvchiga 6 soatda bir martadan ko'p emas).
"""

import asyncio
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from sqlalchemy import select

from db.models import Meta, User, WeeklyAward
from db.session import SessionLocal
from services.certificate import issue_weekly_certificate
from services.league import _week_start_utc, refresh_ranks, weekly_top3
from services.stats import TASHKENT_OFFSET

ROLLOVER_HOUR = 9  # dushanba, Toshkent vaqti
CHECK_INTERVAL = 1200  # 20 daqiqa
NOTICE_COOLDOWN_HOURS = 6
NOTICE_TOP_N = 10  # faqat yuqori o'rinlar uchun xabar beramiz
ROLLOVER_KEY = "weekly_rollover_done"

RANK_ICON = {1: "🥇", 2: "🥈", 3: "🥉"}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _local_now() -> datetime:
    return _now() + TASHKENT_OFFSET


def _week_label(week_start: datetime) -> str:
    """'14.07 — 20.07.2026' ko'rinishidagi hafta yorlig'i (Toshkent)."""
    start_local = week_start + TASHKENT_OFFSET
    end_local = start_local + timedelta(days=6)
    return f"{start_local.strftime('%d.%m')} — {end_local.strftime('%d.%m.%Y')}"


async def _rollover(bot: Bot) -> None:
    """O'tgan haftaning g'oliblarini aniqlab, sertifikat beradi."""
    prev_week_start = _week_start_utc() - timedelta(days=7)
    week_key = (prev_week_start + TASHKENT_OFFSET).strftime("%Y-%m-%d")

    async with SessionLocal() as session:
        marker = (
            await session.execute(select(Meta).where(Meta.key == ROLLOVER_KEY))
        ).scalar_one_or_none()
        if marker and marker.value == week_key:
            return  # bu hafta allaqachon yakunlangan

        winners = await weekly_top3(session, prev_week_start)
        label = _week_label(prev_week_start)

        for user_id, name, xp, rank in winners:
            exists = (
                await session.execute(
                    select(WeeklyAward).where(
                        WeeklyAward.user_id == user_id,
                        WeeklyAward.week_start == week_key,
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
                cert = await issue_weekly_certificate(
                    session, user_id, user.name or name, rank, xp, label
                )
            except Exception as e:
                print(f"Haftalik sertifikat xatosi (user={user_id}): {e!r}")
                continue

            session.add(
                WeeklyAward(
                    user_id=user_id,
                    week_start=week_key,
                    rank=rank,
                    weekly_xp=xp,
                    cert_id=cert.cert_id,
                )
            )
            await session.commit()

            try:
                from aiogram.types import FSInputFile

                await bot.send_photo(
                    user.tg_id,
                    FSInputFile(cert.png_path),
                    caption=(
                        f"{RANK_ICON.get(rank, '🏅')} <b>Haftalik reyting: "
                        f"{rank}-o'rin!</b>\n\n"
                        f"{label} haftasida {xp} XP to'pladingiz. "
                        f"Sovrin sertifikatingiz tayyor — tabriklaymiz!"
                    ),
                    parse_mode="HTML",
                )
            except Exception:
                pass

        # Yakunlangan deb belgilaymiz (g'olib bo'lmasa ham — takror urinmaslik uchun)
        if marker:
            marker.value = week_key
        else:
            marker = Meta(key=ROLLOVER_KEY, value=week_key)
        session.add(marker)
        await session.commit()


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
            await _notify_rank_drops(bot)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"Haftalik reyting xatosi: {e!r}")
        await asyncio.sleep(CHECK_INTERVAL)
