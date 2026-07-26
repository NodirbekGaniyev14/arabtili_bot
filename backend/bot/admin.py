"""Admin bot buyruqlari — faqat ADMIN_ID uchun."""

import asyncio

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message

from config import settings
from db.session import SessionLocal
from services import admin

router = Router()


def _is_admin(message: Message) -> bool:
    return bool(settings.admin_id) and message.from_user is not None and (
        message.from_user.id == settings.admin_id
    )


@router.message(Command("admin", "stats"))
async def cmd_admin(message: Message):
    if not _is_admin(message):
        return
    async with SessionLocal() as session:
        text = await admin.overview(session)
    await message.answer(text, parse_mode="HTML")


@router.message(Command("funnel"))
async def cmd_funnel(message: Message):
    if not _is_admin(message):
        return
    parts = (message.text or "").split(maxsplit=1)
    level = parts[1].strip().upper() if len(parts) > 1 else "A0"
    async with SessionLocal() as session:
        text = await admin.funnel(session, level)
    await message.answer(text, parse_mode="HTML")


@router.message(Command("retention"))
async def cmd_retention(message: Message):
    if not _is_admin(message):
        return
    async with SessionLocal() as session:
        text = await admin.retention(session)
    await message.answer(text, parse_mode="HTML")


@router.message(Command("ratings"))
async def cmd_ratings(message: Message):
    if not _is_admin(message):
        return
    async with SessionLocal() as session:
        text = await admin.ratings_report(session)
    await message.answer(text, parse_mode="HTML")


@router.message(Command("users"))
async def cmd_users(message: Message):
    if not _is_admin(message):
        return
    async with SessionLocal() as session:
        text = await admin.recent_users(session)
    await message.answer(text, parse_mode="HTML")


@router.message(Command("user"))
async def cmd_user(message: Message):
    if not _is_admin(message):
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().lstrip("-").isdigit():
        await message.answer(
            "Foydalanish: <code>/user &lt;telegram_id&gt;</code>\n"
            "Masalan: <code>/user 5000431126</code>",
            parse_mode="HTML",
        )
        return
    async with SessionLocal() as session:
        text = await admin.user_detail(session, int(parts[1].strip()))
    await message.answer(text, parse_mode="HTML")


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, bot: Bot):
    if not _is_admin(message):
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer(
            "Foydalanish: <code>/broadcast xabar matni</code>\n"
            "Barcha foydalanuvchilarga yuboriladi.",
            parse_mode="HTML",
        )
        return

    text = parts[1].strip()
    async with SessionLocal() as session:
        ids = await admin.all_real_tg_ids(session)

    await message.answer(f"📤 {len(ids)} ta foydalanuvchiga yuborilmoqda...")

    sent = failed = 0
    for tg_id in ids:
        try:
            await bot.send_message(tg_id, text)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)  # Telegram limitidan oshmaslik uchun

    await message.answer(
        f"✅ Yuborildi: {sent}\n❌ Yetib bormadi: {failed}"
    )
