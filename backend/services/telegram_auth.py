"""Telegram Mini App initData'ni HMAC-SHA256 bilan tekshirish.

Har bir API so'rov X-Init-Data sarlavhasida Telegram bergan initData'ni
yuboradi — bu foydalanuvchini soxtalashtirib bo'lmasligini kafolatlaydi.
"""

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import dev_auth_active, settings
from db.models import User
from db.session import get_session

# initData qancha vaqt amal qiladi (Telegram tavsiyasi: 1 kundan oshmasin)
MAX_AUTH_AGE_SECONDS = 24 * 60 * 60


def validate_init_data(init_data: str, bot_token: str) -> dict | None:
    """To'g'ri imzolangan va muddati o'tmagan bo'lsa Telegram user dict'ini
    qaytaradi, aks holda None."""
    try:
        parsed = dict(parse_qsl(init_data, keep_blank_values=True))
        received_hash = parsed.pop("hash", None)
        if not received_hash:
            return None

        # Muddat: eski initData qayta ishlatilmasin (replay hujumiga qarshi)
        try:
            auth_age = time.time() - int(parsed.get("auth_date", "0"))
        except ValueError:
            return None
        if auth_age > MAX_AUTH_AGE_SECONDS or auth_age < -300:
            return None

        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(parsed.items())
        )
        secret_key = hmac.new(
            b"WebAppData", bot_token.encode(), hashlib.sha256
        ).digest()
        computed_hash = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(computed_hash, received_hash):
            return None

        return json.loads(parsed.get("user", "{}"))
    except Exception:
        return None


async def get_current_user(
    x_init_data: str = Header(default=""),
    session: AsyncSession = Depends(get_session),
) -> User:
    tg_user = validate_init_data(x_init_data, settings.bot_token) if x_init_data else None

    if tg_user is None:
        if dev_auth_active():
            # Dev rejim: Telegram tashqarisidan test qilish uchun
            tg_user = {"id": 1, "first_name": "Dev", "username": "dev"}
        else:
            raise HTTPException(status_code=401, detail="initData yaroqsiz")

    tg_id = int(tg_user.get("id", 0))
    result = await session.execute(select(User).where(User.tg_id == tg_id))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            tg_id=tg_id,
            name=tg_user.get("first_name", ""),
            username=tg_user.get("username") or "",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    return user
