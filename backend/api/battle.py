"""Oktagon (K25) — WebSocket /ws/battle (jang) va REST /api/battle/* (lobbi, reyting, tarix).

WebSocket protokoli (JSON, «t» — turi):
  klient → server: auth {init} (birinchi xabar), join {level}, cancel, answer {i, choice}, leave, ping
  server → klient: hello, queued, matched, q, opp_answered, round, end, error, pong
Brauzer WebSocket'ga sarlavha qo'sha olmaydi — initData birinchi xabarda keladi (URL'da emas —
nginx loglariga tushmasin).
"""

import asyncio
import logging

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import dev_auth_active, settings
from db.models import User
from db.session import get_session
from services import battle as bt
from services import billing, vocab
from services.telegram_auth import get_current_user, validate_init_data

log = logging.getLogger(__name__)
router = APIRouter()

AUTH_TIMEOUT = 10.0


async def _user_level(session: AsyncSession, user_id: int) -> str:
    from api.v2 import _user_level as lvl

    level = await lvl(session, user_id)
    return level if level in vocab.LEVELS else "A0"


async def _me(session: AsyncSession, user: User) -> dict:
    vip = billing.is_vip(user)
    return {
        "name": user.name or "O'quvchi",
        "points": user.battle_points or 0,
        "league": bt.league(user.battle_points or 0),
        "games": user.battle_games or 0,
        "wins": user.battle_wins or 0,
        "rank": await bt.rank_of(session, user),
        "level": await _user_level(session, user.id),
        "today": await bt.today_count(session, user.id),
        "daily_limit": 0 if vip else bt.FREE_DAILY,  # 0 — cheksiz (VIP)
        "vip": vip,
    }


# ───────────────────────── REST ─────────────────────────


@router.get("/api/battle/me")
async def battle_me(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    return {
        **(await _me(session, user)),
        "online": bt.HUB.online(),
        "levels": list(vocab.LEVELS),
        "rules": {"questions": bt.QUESTIONS, "seconds": bt.QUESTION_SECONDS, "bot_wait": bt.BOT_WAIT},
    }


@router.get("/api/battle/top")
async def battle_top(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    return {
        "items": await bt.top(session, 50),
        "me": {"rank": await bt.rank_of(session, user), "points": user.battle_points or 0},
    }


@router.get("/api/battle/history")
async def battle_history(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    return {"items": await bt.history(session, user.id, 30)}


# ───────────────────────── WebSocket ─────────────────────────


class WSConn:
    def __init__(self, ws: WebSocket):
        self.ws = ws

    async def send(self, msg: dict) -> None:
        await self.ws.send_json(msg)


async def _auth_user(init_data: str) -> User | None:
    tg_user = validate_init_data(init_data, settings.bot_token) if init_data else None
    if tg_user is None:
        if not dev_auth_active():
            return None
        tg_user = {"id": 1, "first_name": "Dev", "username": "dev"}
    tg_id = int(tg_user.get("id", 0) or 0)
    if not tg_id:
        return None
    async with bt.sessions() as session:
        user = (await session.execute(select(User).where(User.tg_id == tg_id))).scalar_one_or_none()
        if user is None:
            user = User(tg_id=tg_id, name=tg_user.get("first_name", ""), username=tg_user.get("username") or "")
            session.add(user)
            await session.commit()
            await session.refresh(user)
        return user


async def _handle_join(conn: WSConn, user_id: int, level: str) -> None:
    level = (level or "").upper()
    async with bt.sessions() as session:
        user = await session.get(User, user_id)
        if user is None:
            return
        if level not in vocab.LEVELS:
            level = await _user_level(session, user_id)
        vip = billing.is_vip(user)
        used = await bt.today_count(session, user_id)
        if not vip and used >= bt.FREE_DAILY:
            await conn.send(
                {
                    "t": "error",
                    "code": "limit",
                    "msg": f"Bugungi {bt.FREE_DAILY} ta bepul jang tugadi — ertaga yana! VIP'da cheksiz.",
                }
            )
            return
        name, points = user.name or "O'quvchi", user.battle_points or 0
    status = await bt.HUB.join(user_id, name, points, level, conn)
    if status == "busy":
        await conn.send({"t": "error", "code": "busy", "msg": "Sizda davom etayotgan jang bor"})
    elif status == "queued":
        await conn.send({"t": "queued", "level": level, "wait": bt.BOT_WAIT, "in_queue": bt.HUB.in_queue(level)})


@router.websocket("/ws/battle")
async def battle_ws(ws: WebSocket):
    await ws.accept()
    try:
        first = await asyncio.wait_for(ws.receive_json(), timeout=AUTH_TIMEOUT)
    except Exception:
        await ws.close(code=4001)
        return
    user = await _auth_user(str(first.get("init", "")) if isinstance(first, dict) and first.get("t") == "auth" else "")
    if user is None:
        await ws.send_json({"t": "error", "code": "auth", "msg": "Kirish tasdiqlanmadi — ilovani qayta oching"})
        await ws.close(code=4003)
        return

    uid = user.id
    conn = WSConn(ws)
    resumed = await bt.HUB.connect(uid, conn)
    try:
        if not resumed:
            await conn.send({"t": "hello", "online": bt.HUB.online()})
        while True:
            msg = await ws.receive_json()
            if not isinstance(msg, dict):
                continue
            t = msg.get("t")
            if t == "join":
                await _handle_join(conn, uid, str(msg.get("level", "")))
            elif t == "cancel":
                bt.HUB.cancel(uid)
                await conn.send({"t": "cancelled"})
            elif t == "answer":
                try:
                    i = int(msg.get("i", -1))
                except (TypeError, ValueError):
                    continue
                bt.HUB.answer(uid, i, str(msg.get("choice", ""))[:300])
            elif t == "leave":
                bt.HUB.leave(uid)
            elif t == "ping":
                await conn.send({"t": "pong", "online": bt.HUB.online()})
    except WebSocketDisconnect:
        pass
    except Exception as e:  # noto'g'ri JSON va h.k. — ulanish yopiladi
        log.debug("Oktagon WS: %r", e)
    finally:
        bt.HUB.disconnect(uid, conn)
