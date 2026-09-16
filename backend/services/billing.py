"""VIP tarif va to'lov (K17.2).

Oqim: paywall (narx, karta, 3 qadam) → o'quvchi bank ilovasidan kartaga
o'tkazadi → chek skrinshotini yuklaydi → adminga Telegram'da rasm + tugmalar
keladi → admin «✅ 1 oy / 3 oy» bosadi → users.vip_until uzayadi, o'quvchiga
xabar. Hech qanday to'lov tizimi integratsiyasi yo'q — pul to'g'ridan-to'g'ri
adminning kartasiga tushadi (.env: PAY_CARD_NUMBER / PAY_CARD_HOLDER).

Chegirma taymeri: paywall birinchi ochilganida users.paywall_seen_at
yoziladi, PAY_DISCOUNT_HOURS o'tgach «eski narx» ko'rsatiladi
(PAY_OLD_PRICE_MONTH=0 bo'lsa taymer ham, chegirma ham yo'q).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import BASE_DIR, settings
from db.models import LessonRating, PaymentRequest, Progress, User, utcnow

log = logging.getLogger(__name__)

PLANS: dict[str, dict] = {
    "1oy": {"days": 30, "title": "1 oylik VIP", "months": 1},
    "3oy": {"days": 90, "title": "3 oylik VIP", "months": 3},
}

MAX_RECEIPT_BYTES = 6 * 1024 * 1024
RECEIPT_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


def _iso(dt: datetime | None) -> str | None:
    """Naive UTC → ISO + 'Z' (aks holda brauzer mahalliy vaqt deb o'qiydi)."""
    return dt.isoformat(timespec="seconds") + "Z" if dt else None


def receipts_dir() -> Path:
    base = Path(settings.db_path).parent if settings.db_path else BASE_DIR / "data"
    d = base / "receipts"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── VIP holati ──


def is_vip(user: User) -> bool:
    return bool(user.vip_until and user.vip_until > utcnow())


def vip_days_left(user: User) -> int:
    if not is_vip(user):
        return 0
    return max((user.vip_until - utcnow()).days, 0) + 1


def grant(user: User, days: int) -> datetime:
    """VIP muddatini uzaytiradi: faol bo'lsa oxiridan, bo'lmasa bugundan."""
    base = user.vip_until if is_vip(user) else utcnow()
    user.vip_until = base + timedelta(days=days)
    return user.vip_until


# ── Narxlar va chegirma ──


def plan_price(plan: str, discount: bool) -> int:
    if plan == "3oy":
        old = settings.pay_old_price_3month or settings.pay_old_price_month * 3
        return settings.pay_price_3month if discount else old
    return settings.pay_price_month if discount else settings.pay_old_price_month


def discount_enabled() -> bool:
    return settings.pay_old_price_month > settings.pay_price_month > 0


def discount_until(user: User) -> datetime | None:
    if not discount_enabled() or not user.paywall_seen_at:
        return None
    return user.paywall_seen_at + timedelta(hours=settings.pay_discount_hours)


def discount_active(user: User) -> bool:
    if not discount_enabled():
        return False  # chegirma o'chiq — «oddiy» narx = pay_price_month
    until = discount_until(user)
    return bool(until and until > utcnow())


def current_price(plan: str, user: User) -> int:
    """Hozir shu foydalanuvchi uchun amaldagi narx."""
    if not discount_enabled():
        return settings.pay_price_3month if plan == "3oy" else settings.pay_price_month
    return plan_price(plan, discount_active(user))


def format_card(number: str) -> str:
    digits = re.sub(r"\D", "", number or "")
    return " ".join(digits[i : i + 4] for i in range(0, len(digits), 4))


def discount_percent(plan: str = "1oy") -> int:
    """Chegirma foizi shu tarif uchun (eski → yangi narx): 1 oy 90k→40k, 3 oy 240k→100k."""
    if not discount_enabled():
        return 0
    old, new = plan_price(plan, False), plan_price(plan, True)
    return round(100 * (1 - new / old)) if old > new > 0 else 0


def price_summary() -> dict:
    """Bosh sahifa/profil yorliqlari uchun qisqa narx: oylik va kunlik."""
    month = settings.pay_price_month
    return {"month": month, "per_day": round(month / 30)}


async def has_pending(session: AsyncSession, user_id: int) -> bool:
    row = (
        await session.execute(
            select(PaymentRequest.id)
            .where(PaymentRequest.user_id == user_id, PaymentRequest.status == "pending")
            .limit(1)
        )
    ).scalar_one_or_none()
    return row is not None


async def social_proof(session: AsyncSession) -> dict:
    """Haqiqiy raqamlar — o'ylab topilgan sharhlar emas."""
    learners = (
        await session.execute(select(func.count(User.id)).where(User.is_demo == 0))
    ).scalar_one()
    lessons = (
        await session.execute(select(func.count(Progress.id)).where(Progress.passed == 1))
    ).scalar_one()
    up = (
        await session.execute(select(func.count(LessonRating.id)).where(LessonRating.rating > 0))
    ).scalar_one()
    total = (await session.execute(select(func.count(LessonRating.id)))).scalar_one()
    return {
        "learners": int(learners or 0),
        "lessons_done": int(lessons or 0),
        "like_percent": round(100 * up / total) if total else 0,
        "ratings": int(total or 0),
    }


def testimonials() -> list[dict]:
    """Admin qo'lda kiritgan haqiqiy fikrlar: content/testimonials.json."""
    import json

    path = BASE_DIR / "content" / "testimonials.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [t for t in data.get("items", []) if t.get("text")][:10]
    except Exception:
        return []


async def all_testimonials(session: AsyncSession) -> list[dict]:
    """Bot orqali rozilik bilan yig'ilgan fikrlar (DB) + qo'lda kiritilganlar (json)."""
    from db.models import Testimonial

    rows = (
        await session.execute(
            select(Testimonial)
            .where(Testimonial.published == 1)
            .order_by(Testimonial.id.desc())
            .limit(10)
        )
    ).scalars().all()
    out = [{"name": t.name, "text": t.text, "level": t.level} for t in rows if t.text]
    return (out + testimonials())[:10]


async def info(session: AsyncSession, user: User) -> dict:
    """Paywall uchun hamma ma'lumot. Birinchi ochilishda taymer boshlanadi."""
    if user.paywall_seen_at is None:
        user.paywall_seen_at = utcnow()
        await session.commit()
    from services import referral

    active = discount_active(user)
    until = discount_until(user)
    return {
        "trial_available": referral.trial_available(user),
        "trial_days": referral.TRIAL_DAYS,
        "referral_days": referral.REF_DAYS,
        "vip": is_vip(user),
        "vip_until": _iso(user.vip_until),
        "vip_days_left": vip_days_left(user),
        "pending": await has_pending(session, user.id),
        "card_number": format_card(settings.pay_card_number),
        "card_holder": settings.pay_card_holder,
        "support_username": settings.support_username.lstrip("@"),
        "discount": {
            "enabled": discount_enabled(),
            "active": active,
            "percent": discount_percent("1oy") if active else 0,
            "until": _iso(until),
            "hours": settings.pay_discount_hours,
        },
        "plans": [
            {
                "id": pid,
                "title": p["title"],
                "days": p["days"],
                "months": p["months"],
                "price": current_price(pid, user),
                # Chegirma faol bo'lsa ustidan chizilgan eski narx, aks holda 0
                "old_price": plan_price(pid, False) if active else 0,
                "discount_percent": discount_percent(pid) if active else 0,
                "per_day": round(current_price(pid, user) / p["days"]),
                "per_month": round(current_price(pid, user) / p["months"]),
            }
            for pid, p in PLANS.items()
        ],
        "proof": await social_proof(session),
        "testimonials": await all_testimonials(session),
    }


# ── Chek va tasdiqlash ──


async def create_request(
    session: AsyncSession, user: User, plan: str, data: bytes, mime: str
) -> PaymentRequest:
    ext = RECEIPT_TYPES[mime]
    req = PaymentRequest(user_id=user.id, plan=plan, amount=current_price(plan, user))
    session.add(req)
    await session.flush()
    path = receipts_dir() / f"{req.id}_{user.tg_id}.{ext}"
    path.write_bytes(data)
    req.receipt_path = str(path)
    await session.commit()
    await session.refresh(req)
    return req


def admin_caption(req: PaymentRequest, user: User) -> str:
    plan = PLANS.get(req.plan, PLANS["1oy"])
    uname = f"@{user.username}" if user.username else "username yo'q"
    return (
        f"💳 <b>Yangi to'lov cheki #{req.id}</b>\n\n"
        f"👤 {user.name or '—'} ({uname})\n"
        f"🆔 <code>{user.tg_id}</code>\n"
        f"📦 {plan['title']} — <b>{req.amount:,}</b> so'm\n"
        f"📅 {req.created_at:%d.%m.%Y %H:%M} UTC\n\n"
        "Chekni tekshiring va muddatni tanlang:"
    ).replace(",", " ")


def admin_keyboard(req_id: int):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ 1 oy", callback_data=f"pay:ok:{req_id}:30"),
                InlineKeyboardButton(text="✅ 3 oy", callback_data=f"pay:ok:{req_id}:90"),
            ],
            [InlineKeyboardButton(text="❌ Rad etish", callback_data=f"pay:no:{req_id}")],
        ]
    )


async def notify_admin(bot, req: PaymentRequest, user: User) -> None:
    """Chek rasmini adminga tugmalar bilan yuboradi. Bot yo'q bo'lsa jim."""
    if not (bot and settings.admin_id):
        return
    try:
        from aiogram.types import BufferedInputFile

        path = Path(req.receipt_path)
        photo = BufferedInputFile(path.read_bytes(), filename=path.name)
        await bot.send_photo(
            settings.admin_id,
            photo,
            caption=admin_caption(req, user),
            parse_mode="HTML",
            reply_markup=admin_keyboard(req.id),
        )
    except Exception as e:
        log.warning("To'lov xabari adminga yetmadi: %r", e)


async def load_request(
    session: AsyncSession, req_id: int
) -> tuple[PaymentRequest, User] | None:
    row = (
        await session.execute(
            select(PaymentRequest, User)
            .join(User, User.id == PaymentRequest.user_id)
            .where(PaymentRequest.id == req_id)
        )
    ).first()
    return (row[0], row[1]) if row else None


async def approve(session: AsyncSession, req: PaymentRequest, user: User, days: int) -> datetime:
    """Chekni tasdiqlaydi va VIP muddatini beradi (qayta bosilsa ikkilanmaydi)."""
    if req.status == "approved":
        return user.vip_until
    until = grant(user, days)
    req.status = "approved"
    req.days = days
    req.decided_at = utcnow()
    await session.commit()
    return until


async def reject(session: AsyncSession, req: PaymentRequest) -> None:
    if req.status != "pending":
        return
    req.status = "rejected"
    req.decided_at = utcnow()
    await session.commit()


def user_approved_text(days: int, until: datetime) -> str:
    return (
        "🎉 <b>VIP yoqildi!</b>\n\n"
        f"Muddat: <b>{days} kun</b> — {until:%d.%m.%Y} gacha.\n"
        "Ilovada 🤖 AI ustoz, 🎤 speaking va 🎯 mock imtihonlar ochiq. "
        "Omad!"
    )


def user_rejected_text() -> str:
    sup = f"@{settings.support_username.lstrip('@')}" if settings.support_username else "admin"
    return (
        "❌ <b>To'lov cheki tasdiqlanmadi.</b>\n\n"
        f"Chek o'qilmagan yoki summa mos kelmagan bo'lishi mumkin. Iltimos, {sup} "
        "bilan bog'laning yoki chekni qayta yuboring."
    )


async def pending_list(session: AsyncSession) -> list[tuple[PaymentRequest, User]]:
    rows = (
        await session.execute(
            select(PaymentRequest, User)
            .join(User, User.id == PaymentRequest.user_id)
            .where(PaymentRequest.status == "pending")
            .order_by(PaymentRequest.id.asc())
            .limit(30)
        )
    ).all()
    return [(r[0], r[1]) for r in rows]
