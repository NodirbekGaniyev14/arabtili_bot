"""Deploy xabari — kod versiyasi (git commit) o'zgarganda foydalanuvchilarga
'bot yangilandi' xabarini bir marta yuboradi."""

import asyncio
import subprocess

from aiogram import Bot
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
)
from sqlalchemy import select

from config import BASE_DIR, settings
from db.models import Meta, User
from db.session import SessionLocal

VERSION_KEY = "deploy_version"

UPDATE_TEXT = (
    "🔄 <b>Bot yangilandi!</b>\n\n"
    "Yangi imkoniyatlar va yaxshilanishlar qo'shildi. "
    "Ochib, davom eting 👇"
)


def current_version() -> str | None:
    """Joriy git commit hash (qisqa). Git yo'q/repo emas bo'lsa None."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode == 0:
            return out.stdout.strip() or None
    except Exception:
        pass
    return None


async def notify_if_updated(bot: Bot) -> None:
    version = current_version()
    if not version:
        return

    async with SessionLocal() as session:
        row = (
            await session.execute(select(Meta).where(Meta.key == VERSION_KEY))
        ).scalar_one_or_none()

        # Birinchi ishga tushish — versiyani saqlaymiz, xabar yubormaymiz
        if row is None:
            session.add(Meta(key=VERSION_KEY, value=version))
            await session.commit()
            return

        if row.value == version:
            return  # o'zgarish yo'q

        # Versiya o'zgardi → barcha haqiqiy foydalanuvchilarga xabar
        ids = (
            await session.execute(
                select(User.tg_id).where(User.is_demo == 0)
            )
        ).scalars().all()

        row.value = version
        session.add(row)
        await session.commit()

    kb = None
    if settings.webapp_url.startswith("https://"):
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📚 Ochish",
                        web_app=WebAppInfo(url=settings.webapp_url),
                    )
                ]
            ]
        )

    for tg_id in ids:
        try:
            await bot.send_message(tg_id, UPDATE_TEXT, parse_mode="HTML", reply_markup=kb)
        except Exception:
            pass
        await asyncio.sleep(0.05)  # Telegram limiti
