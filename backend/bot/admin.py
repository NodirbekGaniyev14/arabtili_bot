"""Admin bot buyruqlari — faqat ADMIN_ID uchun."""

import asyncio
from urllib.parse import quote

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramRetryAfter
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from config import settings
from db.models import User
from db.session import SessionLocal
from services import admin
from services import billing
from services import feedback as feedback_svc

router = Router()

BOT_LINK = "https://t.me/JamalArabiy_bot"

# Do'stlarga taklif kampaniyasi (/taklif)
INVITE_TEXT = (
    "🕌 <b>Do'stlaringizni Arabiy'ga taklif qiling!</b>\n\n"
    "Arab tilini noldan o'rganish endi oson — Jamal 🐪 bilan kuniga "
    "10 daqiqa.\n\n"
    "<b>✅ Botda nima bor:</b>\n"
    "🔹 <b>223 ta dars</b> — A0 dan B2 gacha to'liq kurs\n"
    "🔹 <b>3000+ so'z</b> lug'at bo'limi, har biri audio bilan\n"
    "🔹 O'zak–vazn tahlili — bitta o'zakdan o'nlab so'z\n"
    "🔹 Aqlli takrorlash (SRS) — o'rgangan so'z unutilmaydi\n"
    "🔹 Har daraja oxirida imtihon va <b>sertifikat</b> 🎓\n"
    "🔹 Haftalik reyting, chellenj va yutuqlar 🏆\n"
    "🔹 O'qish matnlari, rol o'yin va yozuv mashqlari\n\n"
    "📣 Bir bosishda do'stingizga yuboring — birga o'rganish "
    "qiziqarliroq va natija tezroq keladi!\n\n"
    "<i>Bot butunlay bepul. Telefon yoki planshet — istalgan qurilmadan "
    "ishlaydi.</i>\n\n"
    f"{BOT_LINK}\n\n"
    "👇 Quyidagi tugmani bosing"
)

INVITE_SHARE_TEXT = (
    "Arab tilini noldan o'rganyapman — Jamal 🐪 boti orqali. "
    "223 ta dars, 3000+ so'z, audio va sertifikat. Bepul, kuniga "
    "10 daqiqa. Sen ham qo'shil 👇"
)


def _invite_kb() -> InlineKeyboardMarkup:
    """Telegram'ning ulashish oynasini ochadigan tugma."""
    share = (
        f"https://t.me/share/url?url={quote(BOT_LINK)}"
        f"&text={quote(INVITE_SHARE_TEXT)}"
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👥 Do'stlarga ulashish", url=share)]
        ]
    )


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


async def _send_reply(bot: Bot, feedback_id: int, text: str) -> str:
    """Fikr egasiga anonim javob yuboradi. Natija — adminga ko'rsatiladigan matn."""
    async with SessionLocal() as session:
        row = await feedback_svc.load_with_user(session, feedback_id)
        if row is None:
            return f"❌ #F{feedback_id} topilmadi"
        fb, user = row
        try:
            await bot.send_message(
                user.tg_id, feedback_svc.reply_notice(fb, text), parse_mode="HTML"
            )
        except Exception as e:
            return f"❌ Yetkazilmadi (#F{feedback_id}): {e}"
        await feedback_svc.mark_replied(session, fb, text)
    return f"✅ Javob yuborildi — #F{feedback_id} ({user.name or user.tg_id})"


@router.message(Command("javob"))
async def cmd_javob(message: Message, bot: Bot):
    """/javob <fikr_id> <matn> — fikr egasiga anonim javob."""
    if not _is_admin(message):
        return
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 3 or not parts[1].strip().isdigit() or not parts[2].strip():
        await message.answer(
            "Foydalanish: <code>/javob &lt;fikr_id&gt; javob matni</code>\n"
            "Yoki fikr xabariga oddiy reply qiling.\n\n"
            "Javob faqat o'sha odamga boradi, sizning ismingiz ko'rsatilmaydi.",
            parse_mode="HTML",
        )
        return
    await message.answer(await _send_reply(bot, int(parts[1]), parts[2].strip()))


# DIQQAT: `.regexp()` matn BOSHIDAN qidiradi, `#F<id>` esa o'rtada turadi —
# shuning uchun `.contains()`. Aniq raqam handler ichida ajratiladi.
@router.message(F.reply_to_message.text.contains("#F"))
async def reply_to_feedback(message: Message, bot: Bot):
    """Admin fikr xabariga reply qilsa — o'sha odamga javob ketadi.

    Filtr faqat `#F` yorlig'i bor xabarlarga tushadi, shuning uchun
    boshqa replylar odatdagidek qayta ishlanadi.
    """
    if not _is_admin(message):
        return
    fb_id = feedback_svc.feedback_id_from_text(message.reply_to_message.text or "")
    text = (message.text or "").strip()
    if fb_id is None or not text:
        return
    await message.answer(await _send_reply(bot, fb_id, text))


async def _blast(bot: Bot, ids, text: str, **kwargs) -> tuple[int, int]:
    """Ro'yxatdagi hammaga yuboradi. Natija: (yuborildi, yetmadi).

    Telegram limitga urilsa (429) RetryAfter beradi — kutib bir marta
    qayta urinamiz, aks holda o'sha odam xabarsiz qoladi.
    """
    sent = failed = 0
    for tg_id in ids:
        for attempt in (1, 2):
            try:
                await bot.send_message(tg_id, text, **kwargs)
                sent += 1
                break
            except TelegramRetryAfter as e:
                if attempt == 2:
                    failed += 1
                    break
                await asyncio.sleep(e.retry_after + 1)
            except Exception:
                failed += 1  # bloklagan yoki chatni o'chirgan
                break
        await asyncio.sleep(0.05)  # Telegram limitidan oshmaslik uchun
    return sent, failed


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
    sent, failed = await _blast(bot, ids, text)
    await message.answer(
        f"✅ Yuborildi: {sent}\n❌ Yetib bormadi: {failed}"
    )


@router.message(Command("taklif"))
async def cmd_taklif(message: Message, bot: Bot):
    """Do'stlarga taklif kampaniyasi — ulashish tugmasi bilan.

    `/taklif` — faqat adminga namuna ko'rsatadi (xavfsiz).
    `/taklif yubor` — hamma foydalanuvchiga yuboradi.
    """
    if not _is_admin(message):
        return

    parts = (message.text or "").split(maxsplit=1)
    confirmed = len(parts) > 1 and parts[1].strip().lower() == "yubor"

    async with SessionLocal() as session:
        ids = await admin.all_real_tg_ids(session)

    if not confirmed:
        await message.answer(
            INVITE_TEXT, parse_mode="HTML", reply_markup=_invite_kb(),
            disable_web_page_preview=True,
        )
        await message.answer(
            f"☝️ Namuna. Shu xabar <b>{len(ids)}</b> ta foydalanuvchiga "
            "ketadi.\n\nYuborish uchun: <code>/taklif yubor</code>",
            parse_mode="HTML",
        )
        return

    await message.answer(f"📤 {len(ids)} ta foydalanuvchiga yuborilmoqda...")
    sent, failed = await _blast(
        bot, ids, INVITE_TEXT, parse_mode="HTML",
        reply_markup=_invite_kb(), disable_web_page_preview=True,
    )
    await message.answer(f"✅ Yuborildi: {sent}\n❌ Yetib bormadi: {failed}")


# ─────────────────── VIP to'lovlari (K17.2) ───────────────────


def _is_admin_cb(cb: CallbackQuery) -> bool:
    return bool(settings.admin_id) and cb.from_user is not None and (
        cb.from_user.id == settings.admin_id
    )


@router.callback_query(F.data.startswith("pay:"))
async def cb_payment(cb: CallbackQuery, bot: Bot):
    """Chek ostidagi tugmalar: pay:ok:<id>:<kun> yoki pay:no:<id>."""
    if not _is_admin_cb(cb):
        await cb.answer("Faqat admin", show_alert=True)
        return
    parts = (cb.data or "").split(":")
    action, req_id = parts[1], int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    days = int(parts[3]) if action == "ok" and len(parts) > 3 and parts[3].isdigit() else 0

    async with SessionLocal() as session:
        row = await billing.load_request(session, req_id)
        if row is None:
            await cb.answer("So'rov topilmadi", show_alert=True)
            return
        req, user = row
        if req.status != "pending":
            await cb.answer(f"Allaqachon: {req.status}", show_alert=True)
            return
        if action == "ok" and days > 0:
            until = await billing.approve(session, req, user, days)
            result = f"✅ Tasdiqlandi — {days} kun, {until:%d.%m.%Y} gacha"
            user_text = billing.user_approved_text(days, until)
        else:
            await billing.reject(session, req)
            result = "❌ Rad etildi"
            user_text = billing.user_rejected_text()
        tg_id = user.tg_id

    try:
        await bot.send_message(tg_id, user_text, parse_mode="HTML")
    except Exception:
        result += " (foydalanuvchiga xabar yetmadi)"

    # Tugmalarni olib tashlab, natijani chek ostiga yozamiz
    try:
        caption = (cb.message.caption or "") if cb.message else ""
        await cb.message.edit_caption(
            caption=f"{caption}\n\n<b>{result}</b>", parse_mode="HTML", reply_markup=None
        )
    except Exception:
        pass
    await cb.answer(result)


@router.message(Command("payments"))
async def cmd_payments(message: Message):
    """Tekshirilmagan cheklar ro'yxati."""
    if not _is_admin(message):
        return
    async with SessionLocal() as session:
        rows = await billing.pending_list(session)
    if not rows:
        await message.answer("✅ Kutayotgan chek yo'q.")
        return
    lines = ["💳 <b>Kutayotgan cheklar:</b>\n"]
    for req, user in rows:
        uname = f"@{user.username}" if user.username else "—"
        lines.append(
            f"#{req.id} · {user.name or '—'} ({uname}) · ID <code>{user.tg_id}</code> · "
            f"{billing.PLANS.get(req.plan, {}).get('title', req.plan)} · "
            f"{req.created_at:%d.%m %H:%M}"
        )
    lines.append("\nQo'lda berish: <code>/vip &lt;telegram_id&gt; &lt;kun&gt;</code>")
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("vip"))
async def cmd_vip(message: Message, bot: Bot):
    """`/vip <tg_id> <kun>` — VIP beradi/uzaytiradi; `/vip <tg_id> off` — o'chiradi."""
    if not _is_admin(message):
        return
    parts = (message.text or "").split()
    if len(parts) < 3 or not parts[1].lstrip("-").isdigit():
        await message.answer(
            "Foydalanish:\n<code>/vip 5000431126 30</code> — 30 kun VIP\n"
            "<code>/vip 5000431126 off</code> — o'chirish",
            parse_mode="HTML",
        )
        return
    tg_id = int(parts[1])
    arg = parts[2].lower()

    async with SessionLocal() as session:
        user = (
            await session.execute(select(User).where(User.tg_id == tg_id))
        ).scalar_one_or_none()
        if user is None:
            await message.answer(f"❌ <code>{tg_id}</code> topilmadi.", parse_mode="HTML")
            return
        if arg == "off":
            user.vip_until = None
            await session.commit()
            await message.answer(f"VIP o'chirildi: {user.name or tg_id}")
            return
        if not arg.isdigit() or int(arg) <= 0:
            await message.answer("Kun soni butun son bo'lsin (masalan 30).")
            return
        days = int(arg)
        until = billing.grant(user, days)
        await session.commit()
        name = user.name or str(tg_id)

    try:
        await bot.send_message(tg_id, billing.user_approved_text(days, until), parse_mode="HTML")
        note = ""
    except Exception:
        note = " (foydalanuvchiga xabar yetmadi)"
    await message.answer(f"👑 {name}: VIP {until:%d.%m.%Y} gacha{note}")
