"""VIP to'lov endpointlari (K17.2) — services/billing.py."""

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import User
from db.session import get_session
from services import billing
from services.telegram_auth import get_current_user

router = APIRouter(prefix="/api/pay")


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

    req = await billing.create_request(session, user, plan, data, mime)
    await billing.notify_admin(getattr(request.app.state, "bot", None), req, user)
    return {"ok": True, "request_id": req.id, "status": req.status}
