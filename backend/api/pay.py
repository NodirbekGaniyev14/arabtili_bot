"""VIP to'lov endpointlari (K17.2) — services/billing.py."""

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import User
from db.session import get_session
from services import billing
from services.telegram_auth import get_current_user

router = APIRouter(prefix="/api/pay")


@router.post("/trial")
async def start_trial(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Bir martalik 2 kunlik VIP sinov (K18.1)."""
    from services import referral

    if not referral.trial_available(user):
        raise HTTPException(status_code=409, detail="Sinov allaqachon ishlatilgan yoki VIP faol")
    until = referral.start_trial(user)
    await session.commit()
    return {"ok": True, "days": referral.TRIAL_DAYS, "vip_until": billing._iso(until)}


@router.get("/info")
async def pay_info(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await billing.info(session, user)


@router.post("/receipt")
async def pay_receipt(
    request: Request,
    file: UploadFile = File(...),
    plan: str = Form("1oy"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Chek skrinshoti → saqlanadi → adminga Telegram'da tugmalar bilan boradi."""
    if plan not in billing.PLANS:
        raise HTTPException(status_code=422, detail="Noma'lum tarif")
    mime = (file.content_type or "").split(";")[0].strip().lower()
    if mime not in billing.RECEIPT_TYPES:
        raise HTTPException(status_code=422, detail="Faqat rasm (JPG/PNG) yuklang")
    if await billing.has_pending(session, user.id):
        raise HTTPException(
            status_code=409, detail="Chekingiz allaqachon tekshirilmoqda — kuting"
        )
    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="Fayl bo'sh")
    if len(data) > billing.MAX_RECEIPT_BYTES:
        raise HTTPException(status_code=413, detail="Rasm juda katta (maks. 6 MB)")
    # K28 pentest: MIME'ni klient aytadi — baytlar haqiqatan rasmmi (aks holda admin chekni ko'rmaydi)
    try:
        import io

        from PIL import Image

        Image.open(io.BytesIO(data)).verify()
    except Exception:
        raise HTTPException(status_code=422, detail="Rasm o'qilmadi — chekning skrinshotini JPG/PNG qilib yuboring")

    # K29.3: qalbaki chekka qarshi — takror rasm, ko'p rad etilgan hisob, sutkalik limit admin ko'rmasdan to'xtatiladi
    blocked = await billing.screen_receipt(session, user, data)
    if blocked:
        raise HTTPException(status_code=blocked[0], detail=blocked[1])

    req = await billing.create_request(session, user, plan, data, mime)
    bot = getattr(request.app.state, "bot", None)
    await billing.notify_admin(bot, req, user, await billing.risk_notes(session, req, user, data))
    if bot:
        # Kutish jim o'tmasin: o'quvchi Telegram'ning o'zida ham tasdiq oladi (K29.3 — va'da: SLA_HOURS soat, kunduzi)
        try:
            await bot.send_message(
                user.tg_id,
                f"📥 <b>Chekingiz qabul qilindi (#{req.id}).</b>\n\nKunduzi (08:00–22:00) {billing.SLA_HOURS} soat ichida "
                "tekshirib, VIP'ni yoqamiz — xabar shu yerga keladi.",
                parse_mode="HTML",
            )
        except Exception:
            pass
    return {"ok": True, "request_id": req.id, "status": req.status}
