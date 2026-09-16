"""Deploy xabari — kod versiyasi (git commit) o'zgarganda foydalanuvchilarga
'bot yangilandi' xabarini bir marta yuboradi."""

import asyncio
import subprocess
from pathlib import Path

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


def _version_from_git_files(root=None) -> str | None:
    """`.git/HEAD` → ref → hash, git binarisiz.

    Serverda systemd xizmati boshqa foydalanuvchi nomidan ishlaydi — git
    «dubious ownership» deb rad etadi (yoki PATH'da yo'q). Fayllarni o'qish
    esa har doim ishlaydi. Qaytaradi: 7 belgili qisqa hash."""
    root = Path(root or BASE_DIR)
    try:
        head = (root / ".git" / "HEAD").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not head.startswith("ref:"):
        return head[:7] or None  # detached HEAD — hash to'g'ridan-to'g'ri
    ref = head.split(":", 1)[1].strip()
    try:
        return (root / ".git" / ref).read_text(encoding="utf-8").strip()[:7] or None
    except OSError:
        pass
    # ref packed-refs ichida bo'lishi mumkin (git gc dan keyin)
    try:
        for line in (root / ".git" / "packed-refs").read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1] == ref:
                return parts[0][:7]
    except OSError:
        pass
    return None


def current_version() -> str | None:
    """Joriy git commit hash (qisqa). Avval `git`, bo'lmasa .git fayllaridan;
    repo emas bo'lsa None."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return _version_from_git_files()


def webapp_url_versioned() -> str:
    """Mini App URL + `?v=<commit>` — telefon WebView'i index.html'ni keshlab
    qolmasin (kompyuterda yangi build ko'rinib, telefonda eski qolardi)."""
    url = settings.webapp_url
    v = current_version()
    if not url or not v:
        return url
    return f"{url}{'&' if '?' in url else '?'}v={v}"


async def notify_if_updated(bot: Bot) -> None:
    version = current_version()
    if not version:
        return

    async with SessionLocal() as session:
        row = (
            await session.execute(select(Meta).where(Meta.key == VERSION_KEY))
        ).scalar_one_or_none()

        if row is not None and row.value == version:
            return  # o'zgarish yo'q — xabar yubormaymiz

        # Birinchi ishga tushish yoki versiya o'zgardi → xabar yuboramiz
        ids = (
            await session.execute(
                select(User.tg_id).where(User.is_demo == 0)
            )
        ).scalars().all()

        if row is None:
            session.add(Meta(key=VERSION_KEY, value=version))
        else:
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
                        web_app=WebAppInfo(url=webapp_url_versioned()),
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
