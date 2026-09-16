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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.models import User, utcnow
from services import billing, referral
from services.stats import TASHKENT_OFFSET

log = logging.getLogger(__name__)

CHECK_INTERVAL = 900  # 15 daqiqa
SOON_DAYS = 3  # muddat tugashidan necha kun oldin
DISCOUNT_LEAD = timedelta(hours=2)
EXPIRED_WINDOW = timedelta(days=3)  # bundan eski tugashlar haqida yozmaymiz
QUIET_FROM, QUIET_TO = 22, 8  # foydalanuvchiga xabar yo'q (Toshkent soati)
ADMIN_DIGEST_HOUR = 9

_digest_sent_on = ""  # admin ro'yxati — kun kaliti (xotirada)


def _local(now: datetime) -> datetime:
    return now + TASHKENT_OFFSET


def _quiet(now: datetime) -> bool:
    h = _local(now).hour
    return h >= QUIET_FROM or h < QUIET_TO


def paywall_keyboard(text: str) -> InlineKeyboardMarkup | None:
    """Mini App'ni to'g'ridan-to'g'ri VIP sahifasida ochadi (App.tsx: #vip)."""
    from services.deploy_notify import webapp_url_versioned

    url = webapp_url_versioned()
    if not url.startswith("https://"):
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=text, web_app=WebAppInfo(url=url + "#vip"))]]
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
    price = billing.price_summary()
    name = user.name or "do'stim"
    when = "bugun" if days <= 1 else f"{days} kundan keyin"
    return (
        f"👑 {name}, VIP muddatingiz <b>{when}</b> "
        f"({_local(user.vip_until):%d.%m.%Y}) tugaydi.\n\n"
        "AI ustoz bilan suhbatlar to'xtab qolmasin — hozir uzaytirsangiz, "
        "yangi muddat qolgan kunlar ustiga qo'shiladi.\n"
        f"1 oy — <b>{_sum(price['month'])} so'm</b> ({_sum(price['per_day'])} so'm/kun)."
    )


def expired_text(user: User) -> str:
    from services import referral

    price = billing.price_summary()
    name = user.name or "do'stim"
    if referral.on_trial(user):
        return (
            f"⏰ {name}, {referral.TRIAL_DAYS} kunlik VIP sinov tugadi.\n\n"
            "Yoqdimi? Davom etish — 1 oy "
            f"<b>{_sum(price['month'])} so'm</b> ({_sum(price['per_day'])} so'm/kun). "
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
    name = user.name or "do'stim"
    return (
        f"⏳ {name}, <b>{pct}% chegirmangiz {left_s}dan keyin tugaydi!</b>\n\n"
        f"Hozir VIP 1 oy — <b>{_sum(new)} so'm</b> (keyin {_sum(old)} so'm).\n"
        "AI ustoz, 🎤 speaking va 🎯 mock imtihonlar — cheksiz."
    )


async def _send(bot, user: User, text: str, button: str) -> bool:
    try:
        await bot.send_message(
            user.tg_id, text, parse_mode="HTML", reply_markup=paywall_keyboard(button)
        )
        return True
    except Exception as e:  # botni bloklagan bo'lishi mumkin
        log.info("VIP eslatma yetmadi (%s): %r", user.tg_id, e)
        return False


async def process(session: AsyncSession, bot, now: datetime | None = None) -> dict:
    """Bir tekshiruv aylanishi. Qaytaradi: {"soon", "expired", "discount", "digest"} soni."""
    global _digest_sent_on
    now = now or utcnow()
    sent = {"soon": 0, "expired": 0, "discount": 0, "digest": 0}
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
            if await _send(bot, user, expired_text(user), "👑 VIP olish"):
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
                    f"#{req.id} · {user.name or '—'} ({uname}) · "
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
