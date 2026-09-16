"""Avtomatik to'lov — Telegram Payments orqali Payme / Click (K18.5).

Nega Telegram Payments: Payme va Click ikkalasi ham Telegram'ning rasmiy to'lov
provayderi — BotFather'da bot → Payments → provayder tanlanadi, provayder
kabinetida shartnoma tuzilgach BotFather `provider_token` beradi. Bizga na
webhook, na alohida JSON-RPC endpoint kerak: bot polling'da ishlaydi, to'lov
`pre_checkout_query` → `successful_payment` update'lari bilan keladi.

Oqim: Mini App paywall → `POST /api/pay/invoice` → bot `createInvoiceLink`
→ `WebApp.openInvoice(url)` (Telegram'ning o'z to'lov oynasi, karta raqami
BIZGA kelmaydi) → `pre_checkout_query` (10 s ichida tasdiq) → `successful_payment`
→ `on_success`: VIP muddati, `payment_requests` yozuvi (provider="telegram",
status="approved"), o'quvchiga va adminga xabar. Mini App `/api/pay/info` ni
qayta so'rab VIP holatini ko'radi.

Sozlama: `.env` → PAY_PROVIDER_TOKEN (BotFather'dan), PAY_PROVIDER_NAME (yorliq).
Token bo'sh bo'lsa `enabled()` False — paywall eski chek oqimini ko'rsatadi.
Chek oqimi avto to'lov yoqilganda ham qoladi (o'tkazmani afzal ko'rganlar uchun).
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.models import PaymentRequest, User, utcnow
from services import billing

log = logging.getLogger(__name__)

CURRENCY = "UZS"
PROVIDER = "telegram"  # payment_requests.provider
PAYLOAD_PREFIX = "vip"


def enabled() -> bool:
    """Token bor = paywall'da «Karta bilan to'lash». Bot obyekti endpointda alohida tekshiriladi."""
    return bool(settings.pay_provider_token.strip())


def provider_name() -> str:
    return settings.pay_provider_name or "Payme / Click"


def payload(user: User, plan: str, price: int) -> str:
    """Invoice payload — o'zimizniki, Telegram uni o'zgartirmay qaytaradi."""
    return f"{PAYLOAD_PREFIX}:{plan}:{user.id}:{price}"


def parse_payload(raw: str) -> tuple[str, int, int] | None:
    """'vip:1oy:12:40000' → (plan, users.id, narx so'mda); noto'g'ri bo'lsa None."""
    parts = (raw or "").split(":")
    if len(parts) != 4 or parts[0] != PAYLOAD_PREFIX or parts[1] not in billing.PLANS:
        return None
    if not (parts[2].isdigit() and parts[3].isdigit()):
        return None
    return parts[1], int(parts[2]), int(parts[3])


def invoice_fields(user: User, plan: str) -> dict:
    """createInvoiceLink parametrlari (narx tiyinda: so'm × 100)."""
    from aiogram.types import LabeledPrice

    p = billing.PLANS[plan]
    price = billing.current_price(plan, user)
    return {
        "title": f"Arabiy VIP — {p['title']}",
        "description": (
            f"{p['days']} kun: AI ustoz bilan cheksiz suhbat, speaking, mock imtihonlar. "
            f"Kuniga {settings.tutor_daily_turns} javob."
        ),
        "payload": payload(user, plan, price),
        "provider_token": settings.pay_provider_token.strip(),
        "currency": CURRENCY,
        "prices": [LabeledPrice(label=p["title"], amount=price * 100)],
    }


async def invoice_link(bot, user: User, plan: str) -> tuple[str, int]:
    """(to'lov havolasi, narx so'mda). Bot yoki token yo'q bo'lsa ValueError."""
    if not enabled() or bot is None:
        raise ValueError("Avto to'lov sozlanmagan")
    fields = invoice_fields(user, plan)
    url = await bot.create_invoice_link(**fields)
    return url, fields["prices"][0].amount // 100


async def validate(session: AsyncSession, tg_id: int, raw_payload: str, currency: str, total: int) -> str:
    """pre_checkout tekshiruvi: bo'sh satr = OK, aks holda o'quvchiga ko'rsatiladigan xato."""
    parsed = parse_payload(raw_payload)
    if parsed is None:
        return "To'lov ma'lumoti eskirgan — ilovada VIP sahifasini qayta oching."
    plan, user_id, price = parsed
    if currency != CURRENCY or total != price * 100:
        return "Summa mos kelmadi — ilovada VIP sahifasini qayta oching."
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None or user.tg_id != tg_id:
        return "Hisob topilmadi — /start bosib qayta urinib ko'ring."
    return ""


async def on_success(
    session: AsyncSession, bot, tg_id: int, sp, now: datetime | None = None
) -> PaymentRequest | None:
    """`successful_payment` → VIP + yozuv + xabarlar. Takror update'da (bir xil
    charge_id) hech narsa qilmaydi. `sp` — aiogram SuccessfulPayment."""
    now = now or utcnow()
    charge = sp.telegram_payment_charge_id or ""
    if charge:
        dup = (
            await session.execute(
                select(PaymentRequest.id).where(PaymentRequest.charge_id == charge).limit(1)
            )
        ).scalar_one_or_none()
        if dup is not None:
            return None

    parsed = parse_payload(sp.invoice_payload)
    user = (await session.execute(select(User).where(User.tg_id == tg_id))).scalar_one_or_none()
    if parsed is None or user is None:
        # Pul olindi, lekin kimga/qaysi tarif — noma'lum: adminga qo'lda hal qilish uchun
        log.error("successful_payment tushunilmadi: tg=%s payload=%r", tg_id, sp.invoice_payload)
        await _admin(bot, f"⚠️ To'lov keldi, lekin payload tushunilmadi: tg <code>{tg_id}</code>, "
                          f"{sp.total_amount // 100} {sp.currency}, payload <code>{sp.invoice_payload}</code>. "
                          f"Qo'lda: /vip {tg_id} &lt;kun&gt;")
        return None
    plan, _uid, _price = parsed
    days = billing.PLANS[plan]["days"]
    until = billing.grant(user, days)
    req = PaymentRequest(
        user_id=user.id,
        plan=plan,
        amount=sp.total_amount // 100,
        status="approved",
        days=days,
        provider=PROVIDER,
        charge_id=charge,
        provider_charge_id=sp.provider_payment_charge_id or "",
        created_at=now,
        decided_at=now,
    )
    session.add(req)
    await session.commit()

    if bot is not None:
        try:
            await bot.send_message(user.tg_id, billing.user_approved_text(days, until), parse_mode="HTML")
        except Exception as e:
            log.info("to'lov tasdig'i o'quvchiga yetmadi (%s): %r", user.tg_id, e)
        await _admin(bot, admin_text(req, user))
    return req


def admin_text(req: PaymentRequest, user: User) -> str:
    uname = f"@{user.username}" if user.username else "username yo'q"
    return (
        f"💳 <b>Avto to'lov #{req.id}</b> ({provider_name()})\n"
        f"👤 {user.name or '—'} ({uname}) · <code>{user.tg_id}</code>\n"
        f"📦 {billing.PLANS[req.plan]['title']} — <b>{req.amount:,}</b> so'm · {req.days} kun\n"
        f"VIP {user.vip_until:%d.%m.%Y} gacha."
    ).replace(",", " ")


async def _admin(bot, text: str) -> None:
    if not (bot and settings.admin_id):
        return
    try:
        await bot.send_message(settings.admin_id, text, parse_mode="HTML")
    except Exception as e:
        log.warning("admin to'lov xabari yetmadi: %r", e)
