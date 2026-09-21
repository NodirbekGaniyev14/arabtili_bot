import logging

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)
from sqlalchemy import select

from config import settings
from services.deploy_notify import webapp_url_versioned
from db.models import User
from db.session import SessionLocal
from services import feedback as feedback_svc

log = logging.getLogger(__name__)
router = Router()

WELCOME_TEXT = (
    "السَّلامُ عَلَيْكُم! 🕌\n\n"
    "Men <b>Jamal</b> 🐪 — shaxsiy arab tili murabbiyingiz.\n\n"
    "Birgalikda arab tilini noldan o'rganamiz: avval qisqa suhbat orqali "
    "darajangizni aniqlaymiz, keyin sizga maxsus kunlik reja tuzib beraman.\n\n"
    "Boshlash uchun quyidagi tugmani bosing 👇"
)


async def _attach_referral(message: Message) -> bool:
    """`/start ref<tg_id>` — YANGI foydalanuvchini taklifchiga bog'laydi.
    Mavjud foydalanuvchi havola bilan kirsa hech narsa o'zgarmaydi."""
    from services import referral

    parts = (message.text or "").split(maxsplit=1)
    ref_tg = referral.parse_start_arg(parts[1] if len(parts) > 1 else "")
    if ref_tg is None or message.from_user is None:
        return False
    tg = message.from_user
    async with SessionLocal() as session:
        user = (
            await session.execute(select(User).where(User.tg_id == tg.id))
        ).scalar_one_or_none()
        if user is not None:
            return False  # eski foydalanuvchi — taklif hisoblanmaydi
        user = User(tg_id=tg.id, name=tg.first_name or "", username=tg.username or "")
        session.add(user)
        await session.flush()
        ok = await referral.attach(session, user, ref_tg)
        await session.commit()
        return ok


@router.message(CommandStart())
async def cmd_start(message: Message):
    invited = await _attach_referral(message)
    bonus = (
        "\n\n🎁 <b>Do'stingiz taklifi bilan keldingiz!</b> Birinchi darsni tugatsangiz — "
        "ikkalangizga 3 kun VIP (AI ustoz bilan gaplashish) bepul."
        if invited
        else ""
    )
    # Telegram web_app tugmasi faqat HTTPS URL qabul qiladi
    if settings.webapp_url.startswith("https://"):
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🕌 O'rganishni boshlash",
                        web_app=WebAppInfo(url=webapp_url_versioned()),
                    )
                ]
            ]
        )
        await message.answer(WELCOME_TEXT + bonus, reply_markup=kb, parse_mode="HTML")
    else:
        await message.answer(
            WELCOME_TEXT
            + "\n\n⚠️ <i>WEBAPP_URL sozlanmagan (.env faylida HTTPS manzil "
            "bo'lishi kerak), shuning uchun tugma hozircha ko'rsatilmadi.</i>",
            parse_mode="HTML",
        )


@router.message(Command("fikr"))
async def cmd_fikr(message: Message, bot: Bot):
    """Foydalanuvchi fikri — saqlanadi va adminga yuboriladi."""
    if message.from_user is None:
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer(
            "💬 Fikringizni yozing:\n<code>/fikr bu yerga fikringiz</code>\n\n"
            "Taklif, xato yoki nima yoqqani — hammasi menga yordam beradi!",
            parse_mode="HTML",
        )
        return

    text = parts[1].strip()[:2000]
    tg = message.from_user

    async with SessionLocal() as session:
        user = (
            await session.execute(select(User).where(User.tg_id == tg.id))
        ).scalar_one_or_none()
        if user is None:
            user = User(
                tg_id=tg.id, name=tg.first_name or "", username=tg.username or ""
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
        fb = await feedback_svc.save(
            session, user.id, text, source="bot", context="/fikr"
        )
        await feedback_svc.notify_admin(bot, fb, user)

    await message.answer("Rahmat! Fikringiz men uchun juda muhim. 🌟")


@router.message(Command("hisobot"))
async def cmd_hisobot(message: Message):
    """Joriy hafta speaking hisoboti (dushanbadan hozirgacha) — dushanba xabari bilan bir xil."""
    if message.from_user is None:
        return
    from services import speaking_report

    async with SessionLocal() as session:
        user = (
            await session.execute(select(User).where(User.tg_id == message.from_user.id))
        ).scalar_one_or_none()
        if user is None:
            await message.answer("Avval /start bosing — ilovani ochib, darajangizni aniqlang. 🐪")
            return
        text = await speaking_report.current_text(session, user)
    await message.answer(
        text, parse_mode="HTML", reply_markup=speaking_report.open_kb()
    )


# ─────────────────── So'rovnoma javoblari (K22.0, services/survey.py) ───────────────────


async def _user_by_tg(session, tg_id: int) -> User | None:
    return (await session.execute(select(User).where(User.tg_id == tg_id))).scalar_one_or_none()


@router.callback_query(F.data == "sv:write")
async def survey_write(cb: CallbackQuery):
    """«✍️ Fikr yozish» — keyingi xabar fikr sifatida qabul qilinadi."""
    from services import survey

    async with SessionLocal() as session:
        user = await _user_by_tg(session, cb.from_user.id)
        if user is not None:
            user.survey_pending = 1
            await session.commit()
    await cb.answer()
    if cb.message is not None:
        await cb.message.answer(survey.PROMPT_TEXT)


@router.callback_query(F.data == "sv:ok")
async def survey_ok(cb: CallbackQuery, bot: Bot):
    """«👍 Hammasi yaxshi» — tugma javobi ham fikr sifatida saqlanadi."""
    from services import survey

    async with SessionLocal() as session:
        user = await _user_by_tg(session, cb.from_user.id)
        if user is not None:
            await survey.record(session, bot, user, survey.OK_TEXT, kind="button")
    await cb.answer("Rahmat! 🙏")
    if cb.message is not None:
        await cb.message.answer("Rahmat! 🙏 Yana biror taklif bo'lsa — shu yerga yozib qoldiring.")


@router.message(F.text & ~F.text.startswith("/"))
async def survey_text(message: Message, bot: Bot):
    """So'rovdan keyingi oddiy matn — fikr (faqat survey_pending bo'lganda; boshqa matn avvalgidek e'tiborsiz)."""
    from services import survey

    if message.from_user is None:
        return
    async with SessionLocal() as session:
        user = await _user_by_tg(session, message.from_user.id)
        if user is None or not user.survey_pending:
            return
        _, xp = await survey.record(session, bot, user, (message.text or "")[:2000])
    await message.answer(survey.THANKS + (f" +{xp} XP" if xp else ""))


@router.message(F.voice)
async def survey_voice(message: Message, bot: Bot):
    """So'rovdan keyingi ovozli xabar — STT (o'zbekcha) orqali matnga, fikr sifatida saqlanadi."""
    from services import stt, survey

    if message.from_user is None or message.voice is None:
        return
    async with SessionLocal() as session:
        user = await _user_by_tg(session, message.from_user.id)
        if user is None or not user.survey_pending:
            return
        text = ""
        if stt.available() and message.voice.duration <= 180:
            try:
                f = await bot.get_file(message.voice.file_id)
                buf = await bot.download_file(f.file_path)
                text = await stt.transcribe(buf.read(), "voice.ogg", "audio/ogg", lang="uz")
            except Exception as e:
                log.info("so'rov ovozi o'qilmadi (%s): %r", message.from_user.id, e)
        if not text:
            await message.answer("Ovozni o'qiy olmadim — iltimos, matn bilan yozing ✍️")
            return
        _, xp = await survey.record(session, bot, user, text[:2000], kind="voice")
    await message.answer(survey.THANKS + (f" +{xp} XP" if xp else ""))
