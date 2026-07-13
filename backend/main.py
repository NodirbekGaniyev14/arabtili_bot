import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Windows konsoli ba'zan cp1251 bo'ladi — emoji/arabcha belgilarda
# UnicodeEncodeError bermasligi uchun UTF-8 ga o'tkazamiz
for stream in (sys.stdout, sys.stderr):
    if stream and hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

from aiogram import Bot, Dispatcher
from aiogram.types import (
    BotCommand,
    BotCommandScopeChat,
    BotCommandScopeDefault,
)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routes import router as api_router
from bot.admin import router as admin_router
from bot.handlers import router as bot_router
from config import settings


async def _setup_commands(bot: Bot):
    # Hammaga ko'rinadigan buyruq
    await bot.set_my_commands(
        [BotCommand(command="start", description="Botni ishga tushirish")],
        scope=BotCommandScopeDefault(),
    )
    # Admin buyruqlari — faqat admin chatida ko'rinadi
    if settings.admin_id:
        await bot.set_my_commands(
            [
                BotCommand(command="admin", description="📊 Statistika paneli"),
                BotCommand(command="users", description="👥 Oxirgi foydalanuvchilar"),
                BotCommand(command="user", description="👤 Foydalanuvchi ma'lumoti"),
                BotCommand(command="broadcast", description="📤 Hammaga xabar"),
                BotCommand(command="start", description="Botni ishga tushirish"),
            ],
            scope=BotCommandScopeChat(chat_id=settings.admin_id),
        )

# Prod rejimda React build shu yerdan xizmat qilinadi
WEBAPP_DIST = Path(__file__).resolve().parent.parent / "webapp" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    from db.session import init_db

    await init_db()

    polling_task = None
    reminder_task = None
    bot = None
    if settings.bot_token:
        from services.reminders import reminder_loop

        bot = Bot(token=settings.bot_token)
        dp = Dispatcher()
        dp.include_router(admin_router)  # admin buyruqlari birinchi
        dp.include_router(bot_router)
        await _setup_commands(bot)
        from bot.branding import setup_branding

        await setup_branding(bot)
        # FastAPI bilan bitta processda polling
        polling_task = asyncio.create_task(
            dp.start_polling(bot, handle_signals=False)
        )
        # Kunlik eslatma fon vazifasi
        reminder_task = asyncio.create_task(reminder_loop(bot))
        # Deploy xabari — versiya o'zgargan bo'lsa foydalanuvchilarga bildiradi
        from services.deploy_notify import notify_if_updated

        asyncio.create_task(notify_if_updated(bot))
        print("🤖 Bot polling boshlandi")
    else:
        print("⚠️  BOT_TOKEN yo'q — bot ishga tushmadi (.env faylini to'ldiring)")
    yield
    for task in (polling_task, reminder_task):
        if task:
            task.cancel()
    if bot:
        await bot.session.close()


app = FastAPI(title="Arabiy API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

if WEBAPP_DIST.exists():
    app.mount("/", StaticFiles(directory=WEBAPP_DIST, html=True), name="webapp")
