"""K30 jonli ovozli suhbat — WebSocket relay (services/live_voice.py) va suhbatdan keyingi tahlil.

WebSocket brauzerdan sarlavha (X-Init-Data) yubora olmaydi — Telegram initData birinchi xabarda keladi
(Oktagon /ws/battle bilan bir xil usul). Gemini kaliti faqat serverda.
"""

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, WebSocket
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import dev_auth_active, settings
from db.models import LiveSession, User
from db.session import SessionLocal, get_session
from services import alerts
from services import live_voice as lv
from services.telegram_auth import get_current_user, validate_init_data

log = logging.getLogger(__name__)
router = APIRouter()

AUTH_TIMEOUT = 10
MIN_LEFT_SECONDS = 10  # limit yoqilgan bo'lsa: bundan kam qolsa suhbat boshlanmaydi
# Bir vaqtda: bitta o'quvchi — bitta qo'ng'iroq; server bo'yicha jami (1 vCPU / 1 GB — relay yengil, lekin cheksiz emas)
MAX_CONCURRENT = 30
ACTIVE: set[int] = set()


def sessions():
    """DB sessiyasi (testlar almashtiradi). WebSocket uzoq yashaydi — sessiya faqat kerak paytda ochiladi."""
    return SessionLocal()


async def auth_user(init_data: str) -> User | None:
    tg_user = validate_init_data(init_data, settings.bot_token) if init_data else None
    if tg_user is None:
        if not dev_auth_active():
            return None
        tg_user = {"id": 1, "first_name": "Dev", "username": "dev"}
    tg_id = int(tg_user.get("id", 0) or 0)
    if not tg_id:
        return None
    async with sessions() as session:
        user = (await session.execute(select(User).where(User.tg_id == tg_id))).scalar_one_or_none()
        if user is None:
            user = User(tg_id=tg_id, name=tg_user.get("first_name", ""), username=tg_user.get("username") or "")
            session.add(user)
            await session.commit()
            await session.refresh(user)
        return user


class WSClient:
    """FastAPI WebSocket → relay interfeysi (recv/send)."""

    def __init__(self, ws: WebSocket):
        self.ws = ws
        self.closed = False

    async def recv(self) -> tuple[str, bytes | None]:
        msg = await self.ws.receive()
        if msg.get("type") == "websocket.disconnect":
            self.closed = True
            return ("disconnect", None)
        if msg.get("bytes"):
            return ("audio", msg["bytes"])
        text = msg.get("text")
        if text:
            try:
                data = json.loads(text)
            except ValueError:
                return ("noop", None)
            if isinstance(data, dict) and data.get("type") == "end":
                return ("end", None)
        return ("noop", None)

    async def send(self, payload: dict) -> None:
        if self.closed:
            return
        try:
            await self.ws.send_json(payload)
        except Exception:  # noqa: BLE001 — mijoz uzilgan
            self.closed = True

    async def close(self, code: int = 1000) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            await self.ws.close(code=code)
        except Exception:  # noqa: BLE001
            pass


async def _fail(client: WSClient, code: str, detail: str, close_code: int) -> None:
    await client.send({"type": "error", "code": code, "detail": detail})
    await client.close(close_code)


@router.websocket("/api/v2/live/ws")
async def live_ws(ws: WebSocket):
    await ws.accept()
    client = WSClient(ws)
    try:
        first = await asyncio.wait_for(ws.receive_json(), timeout=AUTH_TIMEOUT)
    except Exception:  # noqa: BLE001
        await client.close(4001)
        return
    if not isinstance(first, dict) or first.get("type") != "start":
        await client.close(4001)
        return
    user = await auth_user(str(first.get("init_data", "")))
    if user is None:
        await _fail(client, "auth", "Kirish tasdiqlanmadi — ilovani qayta oching", 4003)
        return
    if not lv.available():
        await _fail(client, "off", "Jonli suhbat hozircha yoqilmagan", 4004)
        return
    if user.id in ACTIVE:
        await _fail(client, "busy", "Sizda boshqa jonli suhbat ochiq — avvalgisini yoping", 4005)
        return
    if len(ACTIVE) >= MAX_CONCURRENT:
        await _fail(client, "busy", "Hozir jonli suhbat band — bir daqiqadan keyin urinib ko'ring", 4005)
        return
    ACTIVE.add(user.id)  # tekshiruv va qo'shish orasida await yo'q — ikki parallel ulanish ikkalasi ham o'tmaydi
    try:
        await _run(ws, client, user, first)
    finally:
        ACTIVE.discard(user.id)


async def _run(ws: WebSocket, client: WSClient, user: User, first: dict) -> None:
    from api.v2 import _user_level
    from services import tutor

    topic = tutor.TOPIC_BY_ID.get(str(first.get("topic_id") or "erkin")[:24]) or tutor.TOPIC_BY_ID["erkin"]
    async with sessions() as session:
        user = await session.get(User, user.id)
        left = await lv.allowance(session, user)
        level = await _user_level(session, user.id)
        known = await tutor.known_words(session, user.id)
    if left is not None and left < MIN_LEFT_SECONDS:
        await _fail(client, "limit", "Jonli suhbat daqiqalari tugadi", 4002)
        return
    max_seconds = settings.live_max_seconds if left is None else min(settings.live_max_seconds, left)
    system = lv.system_prompt(name=user.name, level=level, topic=topic, known=known)
    bot = getattr(getattr(ws.app, "state", None), "bot", None)

    try:
        async with lv.open_live(system) as live:
            await client.send({"type": "ready", "max_seconds": max_seconds})
            res = await lv.relay(client, live, max_seconds=max_seconds, idle_seconds=settings.live_idle_seconds)
    except lv.LiveUnavailable as e:
        alerts.fire(bot, "live_auth" if e.kind == "auth" else "live_down", str(e.__cause__ or e)[:120])
        await _fail(client, "unavailable", e.message_uz, 1011)
        return
    if res.error:
        log.warning("Jonli suhbat xatosi (user %s, %.0f s): %s", user.id, res.seconds, res.error)
        if res.seconds < 5:  # boshlanishi bilan uzilgan — xizmat muammosi bo'lishi mumkin
            alerts.fire(bot, "live_down", res.error[:120])

    async with sessions() as session:
        user = await session.get(User, user.id)
        row = await lv.save(session, user, topic["id"], level, res)
        spent = await lv.spent_today(session)
    if settings.live_daily_budget_usd > 0 and spent > settings.live_daily_budget_usd:
        alerts.fire(bot, "live_budget", f"${spent:.2f}")
    await client.send({"type": "end", "reason": row.reason, "seconds": row.seconds, "session_id": row.id})
    await client.close()


class LiveReviewBody(BaseModel):
    session_id: int


@router.post("/api/v2/live/review")
async def live_review(
    body: LiveReviewBody,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Suhbatdan keyingi tahlil: xatolar (daftarga), yangi so'zlar, XP — bir marta hisoblanadi."""
    row = await session.get(LiveSession, body.session_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Suhbat topilmadi")
    result = await lv.review(session, row, user)
    return {**result, "topic": row.topic, "transcript": json.loads(row.transcript or "[]")}
