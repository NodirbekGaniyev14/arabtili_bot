"""Kunlik eslatma — kechqurun maqsadni bajarmagan foydalanuvchilarga xabar.

FastAPI lifespan'da fon vazifasi sifatida ishga tushadi. Har foydalanuvchiga
kuniga bir marta (Toshkent vaqti bilan ~20:00 da) yuboriladi.
"""

import asyncio
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
)
from sqlalchemy import select

from config import settings
from db.models import Plan, User
from db.session import SessionLocal
from services.stats import TASHKENT_OFFSET, _today, user_stats

REMINDER_HOUR = 20  # Toshkent vaqti
CHECK_INTERVAL = 900  # 15 daqiqa


def _local_hour() -> int:
    return (datetime.now(timezone.utc).replace(tzinfo=None) + TASHKENT_OFFSET).hour


async def _send_reminders(bot: Bot) -> None:
    today = _today().isoformat()

    async with SessionLocal() as session:
        users = (
            await session.execute(select(User).where(User.is_demo == 0))
        ).scalars().all()

        for user in users:
            if user.notified_date == today:
                continue

            plan = (
                await session.execute(
                    select(Plan)
                    .where(Plan.user_id == user.id)
                    .order_by(Plan.id.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if plan is None:
                continue  # onboardingdan o'tmagan

            stats = await user_stats(
                session, user.id, None  # keyingi dars kerak emas
            )
            if stats["xp_today"] >= plan.daily_xp_goal:
                continue  # maqsad bajarilgan

            remaining = plan.daily_xp_goal - stats["xp_today"]
            name = user.name or "do'stim"
            streak = stats["streak"]
            streak_line = (
                f"🔥 {streak} kunlik streak'ingiz o'chib qolmasin!\n"
                if streak > 0
                else ""
            )
            text = (
                f"Assalomu alaykum, {name}! 🐪\n\n"
                f"{streak_line}"
                f"Bugun arab tilidan mashq qilishni unutmang — "
                f"maqsadingizga atigi {remaining} XP qoldi. "
                f"Bir necha daqiqa ham yetarli!"
            )

            kb = None
            if settings.webapp_url.startswith("https://"):
                kb = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="📚 Davom etish",
                                web_app=WebAppInfo(url=settings.webapp_url),
                            )
                        ]
                    ]
                )

            try:
                await bot.send_message(user.tg_id, text, reply_markup=kb)
            except Exception:
                pass  # foydalanuvchi botni bloklagan bo'lishi mumkin

            user.notified_date = today
            session.add(user)

        await session.commit()


async def reminder_loop(bot: Bot) -> None:
    """Fon halqasi — soatni tekshiradi, vaqti kelganda eslatma yuboradi."""
    while True:
        try:
            if _local_hour() == REMINDER_HOUR:
                await _send_reminders(bot)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"Eslatma xatosi: {e!r}")
        await asyncio.sleep(CHECK_INTERVAL)
