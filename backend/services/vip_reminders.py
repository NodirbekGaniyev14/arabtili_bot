"""VIP eslatmalari (K17.4) — pul qaytib kelishi uchun uchta xabar.

1. VIP muddati 3 kun qolganda va tugagan kuni — «Uzaytirish» tugmasi bilan
   (users.vip_notice = davr kaliti, har VIP davri uchun bir marta).
2. Chegirma taymeri tugashiga 2 soat qolganda — paywall'ni ochib to'lamaganlarga
   bir marta (users.discount_notified).
3. Adminga har kuni 09:00 da tekshirilmagan cheklar ro'yxati (bo'lsa).

`vip_loop` — lifespan'da fon halqasi (reminders.py kabi), 15 daqiqada bir
`process()` ni chaqiradi. Foydalanuvchi xabarlari faqat kunduzi (08–22 Toshkent).
"""

import asyncio
import logging
from datetime import datetime, timedelta

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from services.names import admin_show, esc, show
from services import notify_prefs
from db.models import TutorTurn, User, utcnow
from services import billing, referral
from services.stats import TASHKENT_OFFSET

log = logging.getLogger(__name__)

CHECK_INTERVAL = 900  # 15 daqiqa
SOON_DAYS = 3  # muddat tugashidan necha kun oldin
DISCOUNT_LEAD = timedelta(hours=2)
# K29.2 sinov eslatmalari: yoqilganidan 3 soat o'tib ustozga yozmagan bo'lsa (30 soatgacha), tugashiga 6 soat qolganda
TRIAL_START_AFTER = timedelta(hours=3)
TRIAL_START_UNTIL = timedelta(hours=30)
TRIAL_LAST_LEAD = timedelta(hours=6)
EXPIRED_WINDOW = timedelta(days=3)  # bundan eski tugashlar haqida yozmaymiz
QUIET_FROM, QUIET_TO = 22, 8  # foydalanuvchiga xabar yo'q (Toshkent soati)
ADMIN_DIGEST_HOUR = 9

_digest_sent_on = ""  # admin ro'yxati — kun kaliti (xotirada)


def _local(now: datetime) -> datetime:
    return now + TASHKENT_OFFSET


def _quiet(now: datetime) -> bool:
    h = _local(now).hour
    return h >= QUIET_FROM or h < QUIET_TO


def paywall_keyboard(text: str, page: str = "vip") -> InlineKeyboardMarkup | None:
    """Mini App'ni to'g'ridan-to'g'ri kerakli sahifada ochadi (App.tsx: #vip, #tutor)."""
    from services.deploy_notify import webapp_url_versioned

    url = webapp_url_versioned()
    if not url.startswith("https://"):
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=text, web_app=WebAppInfo(url=f"{url}#{page}"))]]
    )


def _sum(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def soon_key(user: User) -> str:
    return f"soon:{user.vip_until:%Y%m%d%H%M}"


def expired_key(user: User) -> str:
    return f"expired:{user.vip_until:%Y%m%d%H%M}"


def soon_text(user: User, now: datetime) -> str:
    # billing.vip_days_left bilan bir xil formula, lekin berilgan `now` bo'yicha
    # (halqa vaqti / test vaqti) — haqiqiy soatga bog'lanmaydi
    days = max((user.vip_until - now).days, 0) + 1
    price = billing.price_summary(user, now)
    name = show(user.name, "do'stim")
    when = "bugun" if days <= 1 else f"{days} kundan keyin"
    return (
        f"👑 {name}, VIP muddatingiz <b>{when}</b> "
        f"({_local(user.vip_until):%d.%m.%Y}) tugaydi.\n\n"
        "AI ustoz bilan suhbatlar to'xtab qolmasin — hozir uzaytirsangiz, "
        "yangi muddat qolgan kunlar ustiga qo'shiladi.\n"
        f"1 oy — <b>{_sum(price['month'])} so'm</b> ({_sum(price['per_day'])} so'm/kun)."
    )


def expired_text(user: User, turns: int | None = None, now: datetime | None = None) -> str:
    """VIP/sinov tugadi xabari. K29: narx — odamning HAQIQIY narxi (paywall bilan bir xil); sinov tugaganda
    chegirma oynasi yangidan 24 soat boshlanadi (process()), matn shuni aytadi; `turns` — sinovdagi javoblar."""
    from services import referral

    price = billing.price_summary(user, now)
    name = show(user.name, "do'stim")
    if referral.on_trial(user):
        used = f"Sinov davomida {turns} ta suhbat javobi berdingiz. " if turns else ""
        if billing.discount_active(user, now):
            offer = (
                f"⏳ <b>Faqat {settings.pay_discount_hours} soat:</b> 1 oy <b>{_sum(price['month'])} so'm</b> "
                f"(keyin {_sum(billing.plan_price('1oy', False))} so'm) — kuniga {_sum(price['per_day'])} so'm."
            )
        else:
            offer = f"Davom etish — 1 oy <b>{_sum(price['month'])} so'm</b> ({_sum(price['per_day'])} so'm/kun)."
        return (
            f"⏰ {name}, {referral.TRIAL_DAYS} kunlik VIP sinov tugadi.\n\n"
            f"{used}Yoqdimi?\n{offer}\n"
            f"Yoki do'stingizni taklif qiling — ikkalangizga {referral.REF_DAYS} kun VIP bepul."
        )
    return (
        f"⏰ {name}, VIP muddatingiz tugadi.\n\n"
        f"AI ustoz endi kuniga {settings.tutor_free_turns} ta bepul javob bilan ishlaydi, "
        "mock imtihonlar va to'liq speaking VIP'da.\n"
        f"Qayta yoqish — 1 oy <b>{_sum(price['month'])} so'm</b> "
        f"({_sum(price['per_day'])} so'm/kun)."
    )


def discount_text(user: User, now: datetime) -> str:
    until = billing.discount_until(user)
    left = max(int((until - now).total_seconds() // 60), 1)
    left_s = f"{left // 60} soat {left % 60} daqiqa" if left >= 60 else f"{left} daqiqa"
    new, old = billing.plan_price("1oy", True), billing.plan_price("1oy", False)
    pct = billing.discount_percent("1oy")
    name = show(user.name, "do'stim")
    return (
        f"⏳ {name}, <b>{pct}% chegirmangiz {left_s}dan keyin tugaydi!</b>\n\n"
        f"Hozir VIP 1 oy — <b>{_sum(new)} so'm</b> (keyin {_sum(old)} so'm).\n"
        f"AI ustoz (kuniga {settings.tutor_daily_turns} javob), 🎤 speaking va 🎯 kasb bo'yicha mock imtihonlar."
    )


def _hours_left(user: User, now: datetime) -> int:
    return max(int((user.trial_until - now).total_seconds() // 3600), 1)


def trial_start_text(user: User, now: datetime) -> str:
    """K29.2: sinov yoqilgan, lekin ustozga hali yozilmagan — bir daqiqalik birinchi qadam."""
    name = show(user.name, "do'stim")
    return (
        f"🎁 {name}, VIP sinovingiz faol — lekin ustoz sizni hali kutyapti.\n\n"
        "Bir daqiqa: ustozga «Umra» yoki «Safar» mavzusida bitta gap yozing yoki ayting. "
        "Xato qilsangiz — u o'sha zahoti yumshoq tuzatadi, hech kim baho qo'ymaydi.\n\n"
        f"Sinov ~{_hours_left(user, now)} soatdan keyin tugaydi."
    )


def trial_last_text(user: User, turns: int, now: datetime) -> str:
    """K29.2: sinov tugashiga oz qoldi — narx aytilmaydi (tugagach 24 soatlik oyna o'zi ochiladi), qiymat ko'rsatiladi."""
    name = show(user.name, "do'stim")
    used = (
        f"Hozircha {turns} ta suhbat javobi berdingiz. "
        if turns
        else "Hali ustoz bilan gaplashib ko'rmadingiz. "
    )
    offer = "\n\nSinov tugagach 24 soat davomida maxsus narx taklif qilamiz." if billing.discount_enabled() else ""
    return (
        f"⏳ {name}, VIP sinovingiz ~{_hours_left(user, now)} soatdan keyin tugaydi.\n\n"
        f"{used}Qolgan vaqtda VIP'ning eng kuchli qismini sinang: kasb bo'yicha 🎯 mock imtihon — "
        f"5 savol, ball va xatolar tahlili bilan.{offer}"
    )


async def _send(bot, user: User, text: str, button: str, page: str = "vip") -> bool:
    if not notify_prefs.enabled(user, "vip"):
        return False
    try:
        await bot.send_message(
            user.tg_id, text, parse_mode="HTML", reply_markup=paywall_keyboard(button, page)
        )
        return True
    except Exception as e:  # botni bloklagan bo'lishi mumkin
        log.info("VIP eslatma yetmadi (%s): %r", user.tg_id, e)
        return False


async def _trial_turns(session: AsyncSession, user: User) -> int:
    """Sinov davomida berilgan suhbat javoblari (shaxsiy hisobot uchun)."""
    if not user.trial_until:
        return 0
    start = user.trial_until - timedelta(days=referral.TRIAL_DAYS)
    return int(
        (
            await session.execute(
                select(func.count(TutorTurn.id)).where(
                    TutorTurn.user_id == user.id, TutorTurn.created_at >= start, TutorTurn.created_at <= user.trial_until
                )
            )
        ).scalar_one()
        or 0
    )


async def process(session: AsyncSession, bot, now: datetime | None = None) -> dict:
    """Bir tekshiruv aylanishi. Qaytaradi: {"soon", "expired", "discount", "trial", "digest"} soni."""
    global _digest_sent_on
    now = now or utcnow()
    sent = {"soon": 0, "expired": 0, "discount": 0, "trial": 0, "digest": 0}
    real = User.is_demo == 0

    if not _quiet(now):
        # 1a. Muddat tugayapti (3 kun ichida)
        rows = (
            await session.execute(
                select(User).where(
                    real,
                    User.vip_until > now,
                    User.vip_until <= now + timedelta(days=SOON_DAYS),
                )
            )
        ).scalars().all()
        for user in rows:
            if user.vip_notice == soon_key(user):
                continue
            user.vip_notice = soon_key(user)  # yetmasa ham qayta urinmaymiz
            if referral.on_trial(user):
                continue  # 2 kunlik sinovda «tugayapti» — shart emas, tugaganda yozamiz
            if await _send(bot, user, soon_text(user, now), "👑 Uzaytirish"):
                sent["soon"] += 1

        # 1b. Tugagan (oxirgi 3 kun ichida)
        rows = (
            await session.execute(
                select(User).where(
                    real,
                    User.vip_until <= now,
                    User.vip_until > now - EXPIRED_WINDOW,
                )
            )
        ).scalars().all()
        for user in rows:
            if user.vip_notice == expired_key(user):
                continue
            user.vip_notice = expired_key(user)
            turns = None
            if referral.on_trial(user):
                # K29: sinov tugadi — narx oynasi shu paytdan 24 soatga YANGIDAN ochiladi (ilgari paywall birinchi
                # ochilganda boshlangan 24 soat sinov (48 soat) davomida tugab, sinovdan keyin hamma 90 000 ni ko'rardi)
                if billing.discount_enabled():
                    user.paywall_seen_at = now
                    user.discount_notified = 0
                turns = await _trial_turns(session, user)
            if await _send(bot, user, expired_text(user, turns, now), "👑 VIP olish"):
                sent["expired"] += 1

        # 2. Chegirma taymeri tugayapti — paywall'ni ochgan, to'lamagan
        if billing.discount_enabled():
            lead = timedelta(hours=settings.pay_discount_hours)
            rows = (
                await session.execute(
                    select(User).where(
                        real,
                        User.discount_notified == 0,
                        User.paywall_seen_at.is_not(None),
                        # until - 2h <= now < until  ⇔  seen ∈ (now - lead, now - lead + 2h]
                        User.paywall_seen_at > now - lead,
                        User.paywall_seen_at <= now - lead + DISCOUNT_LEAD,
                    )
                )
            ).scalars().all()
            for user in rows:
                if billing.is_vip(user) or await billing.has_pending(session, user.id):
                    continue
                user.discount_notified = 1
                if await _send(bot, user, discount_text(user, now), "🔥 Chegirma bilan olish"):
                    sent["discount"] += 1

        # 3. K29.2: sinovdagilar — 0/39 to'lov sababi «faollashmaslik» bo'lishi mumkin (sinovchi ustozga yozmagan)
        rows = (
            await session.execute(
                select(User).where(
                    real,
                    User.trial_until.is_not(None),
                    User.vip_until == User.trial_until,  # hozirgi VIP aynan sinov
                    User.vip_until > now,
                )
            )
        ).scalars().all()
        for user in rows:
            elapsed = now - (user.trial_until - timedelta(days=referral.TRIAL_DAYS))
            left = user.trial_until - now
            started = False
            if not user.trial_nudge & 1 and elapsed >= TRIAL_START_AFTER:
                user.trial_nudge |= 1  # bir marta; yozgan bo'lsa yoki kech qolgan bo'lsa xabar yo'q
                if elapsed <= TRIAL_START_UNTIL and await _trial_turns(session, user) == 0:
                    started = await _send(bot, user, trial_start_text(user, now), "🤖 Ustozni ochish", "tutor")
                    sent["trial"] += started
            if not started and not user.trial_nudge & 2 and left <= TRIAL_LAST_LEAD:
                user.trial_nudge |= 2
                turns = await _trial_turns(session, user)
                if await _send(bot, user, trial_last_text(user, turns, now), "🎯 Mock imtihonni ochish", "tutor"):
                    sent["trial"] += 1

        await session.commit()

    # 3. Admin: tekshirilmagan cheklar (09:00, kuniga bir marta, bo'lsa)
    day = _local(now).date().isoformat()
    if settings.admin_id and _local(now).hour == ADMIN_DIGEST_HOUR and _digest_sent_on != day:
        _digest_sent_on = day
        pending = await billing.pending_list(session)
        if pending:
            lines = [f"💳 <b>{len(pending)} ta chek tasdiqlanmagan:</b>\n"]
            for req, user in pending:
                wait_h = int((now - req.created_at).total_seconds() // 3600)
                uname = f"@{user.username}" if user.username else "—"
                lines.append(
                    f"#{req.id} · {admin_show(user.name, user.username, user.tg_id)} ({esc(uname)}) · "
                    f"{billing.PLANS.get(req.plan, {}).get('title', req.plan)} · "
                    f"{wait_h} soat kutmoqda"
                )
            lines.append("\nRo'yxat: /payments · Qo'lda: /vip <telegram_id> <kun>")
            try:
                await bot.send_message(settings.admin_id, "\n".join(lines), parse_mode="HTML")
                sent["digest"] = len(pending)
            except Exception as e:
                log.warning("admin chek ro'yxati yuborilmadi: %r", e)
    return sent


async def vip_loop(bot) -> None:
    """Fon halqasi — 15 daqiqada bir VIP/chegirma/chek eslatmalarini tekshiradi."""
    from db.session import SessionLocal

    while True:
        try:
            async with SessionLocal() as session:
                await process(session, bot)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("VIP eslatma xatosi: %r", e)
        await asyncio.sleep(CHECK_INTERVAL)
