from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)

from config import settings

router = Router()

WELCOME_TEXT = (
    "السَّلامُ عَلَيْكُم! 🕌\n\n"
    "Men <b>Jamal</b> 🐪 — shaxsiy arab tili murabbiyingiz.\n\n"
    "Birgalikda arab tilini noldan o'rganamiz: avval qisqa suhbat orqali "
    "darajangizni aniqlaymiz, keyin sizga maxsus kunlik reja tuzib beraman.\n\n"
    "Boshlash uchun quyidagi tugmani bosing 👇"
)


@router.message(CommandStart())
async def cmd_start(message: Message):
    # Telegram web_app tugmasi faqat HTTPS URL qabul qiladi
    if settings.webapp_url.startswith("https://"):
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🕌 O'rganishni boshlash",
                        web_app=WebAppInfo(url=settings.webapp_url),
                    )
                ]
            ]
        )
        await message.answer(WELCOME_TEXT, reply_markup=kb, parse_mode="HTML")
    else:
        await message.answer(
            WELCOME_TEXT
            + "\n\n⚠️ <i>WEBAPP_URL sozlanmagan (.env faylida HTTPS manzil "
            "bo'lishi kerak), shuning uchun tugma hozircha ko'rsatilmadi.</i>",
            parse_mode="HTML",
        )
