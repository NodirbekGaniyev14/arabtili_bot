"""Ulashish kartasi API (K21.5): karta yasash (+ botga yuborish), ochiq PNG fayli."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import User
from db.session import get_session
from services import share_card
from services.telegram_auth import get_current_user

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/share")


class ShareBody(BaseModel):
    send: bool = False  # botga ham yuborilsinmi (do'stlarga forward qilish uchun)


@router.post("/week")
async def share_week(
    body: ShareBody,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Haftalik natija kartasi. {"url": ochiq to'liq URL (story uchun), "path", "sent", "caption"}."""
    path, rel = await share_card.issue(session, user)
    data = await share_card.card_data(session, user)
    cap = share_card.caption(data)
    origin = share_card.public_origin()
    sent = False
    bot = getattr(request.app.state, "bot", None)
    if body.send and bot:
        try:
            from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup

            from services import referral

            kb = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="👥 Do'stlarga ulashish", url=referral.share_url(user))]]
            )
            await bot.send_photo(user.tg_id, FSInputFile(path), caption=cap, reply_markup=kb)
            sent = True
        except Exception as e:  # botni bloklagan / vaqtinchalik xato
            log.info("ulashish kartasi yuborilmadi (%s): %r", user.tg_id, e)
    return {
        "url": f"{origin}{rel}" if origin else rel,
        "path": rel,
        "sent": sent,
        "caption": cap,
        "ref_link": data["ref_link"],
        "streak": data["streak"],
        "week_xp": data["week_xp"],
    }


@router.get("/{file}")
async def share_file(file: str):
    """Karta PNG — ochiq (Telegram story rasmni shu havoladan oladi)."""
    if ".." in file or "/" in file or not file.endswith(".png"):
        raise HTTPException(status_code=404)
    path = share_card.SHARE_DIR / file
    if not path.exists():
        raise HTTPException(status_code=404)
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "public, max-age=3600"})
