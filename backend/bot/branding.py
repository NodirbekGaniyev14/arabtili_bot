"""Bot brendingi — bio (short description) va tanishtiruv (description).

Bot ishga tushganda avtomatik o'rnatiladi (server Telegramga ulanadi).
Botning profil rasmi (logo) esa faqat @BotFather orqali yuklanadi.
"""

from aiogram import Bot

# Bio — profilda ism ostida ko'rinadi (maks 120 belgi)
SHORT_DESCRIPTION = (
    "Arab tilini 0 dan o‘rgatuvchi AI murabbiy 🐪 "
    "Har kuni bir necha daqiqa — alifbodan suhbatgacha."
)

# Tanishtiruv — bo'sh chatda va "bot nima qila oladi" da ko'rinadi (maks 512)
DESCRIPTION = (
    "🕌 Arabiy — arab tilini noldan o‘rganish uchun shaxsiy AI murabbiy.\n\n"
    "Jamal 🐪 darajangizni aniqlaydi va sizga maxsus kunlik reja tuzadi. "
    "Alifbo, talaffuz, so‘z boyligi va suhbat — hammasi qiziqarli mashqlar, "
    "audio va o‘yin uslubida.\n\n"
    "✨ AI shaxsiy reja\n"
    "🔤 Alifbodan boshlab\n"
    "🔊 Haqiqiy talaffuz\n"
    "🔁 Aqlli takror — unutmaslik uchun\n"
    "🔥 Streak, XP va haftalik liga\n\n"
    "Boshlash uchun «Ishga tushirish» tugmasini bosing!"
)


async def setup_branding(bot: Bot) -> None:
    """Bio va tanishtiruvni o'rnatadi (tarmoq xatosida jim o'tadi)."""
    try:
        await bot.set_my_short_description(short_description=SHORT_DESCRIPTION)
        await bot.set_my_description(description=DESCRIPTION)
        print("✅ Bot brendingi (bio + tanishtiruv) o'rnatildi")
    except Exception as e:
        print(f"⚠️  Brendingni o'rnatib bo'lmadi: {e!r}")
