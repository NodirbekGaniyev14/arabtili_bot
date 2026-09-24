"""K25 Oktagon — 1v1 lug'at jangi: ball, liga, savollar, bot, odam↔odam va bot jangi, taslim bo'lish,
WebSocket (imzolangan initData), kunlik limit, REST."""

import asyncio
import hashlib
import hmac
import json
import random
import time
from urllib.parse import urlencode

import httpx
import pytest
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect

from db.models import Battle, User, XpLog, utcnow
from services import battle as bt
from services import vocab


@pytest.fixture(autouse=True)
def fast(monkeypatch, session_factory):
    """Real vaqt emas — tez sinov: 10 s → 0.4 s va h.k.; yangi hub; test bazasi."""
    monkeypatch.setattr(bt, "QUESTION_SECONDS", 0.4)
    monkeypatch.setattr(bt, "GRACE", 0.05)
    monkeypatch.setattr(bt, "ROUND_PAUSE", 0.01)
    monkeypatch.setattr(bt, "START_DELAY", 0.01)
    monkeypatch.setattr(bt, "BOT_WAIT", 0.05)
    monkeypatch.setattr(bt, "SESSION_FACTORY", session_factory)
    monkeypatch.setattr(bt, "HUB", bt.Hub())


class FakeConn:
    def __init__(self):
        self.msgs: list[dict] = []
        self.pos = 0

    async def send(self, msg: dict) -> None:
        self.msgs.append(msg)

    async def wait(self, t: str, timeout: float = 5.0) -> dict:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            while self.pos < len(self.msgs):
                m = self.msgs[self.pos]
                self.pos += 1
                if m.get("t") == t:
                    return m
            await asyncio.sleep(0.005)
        raise AssertionError(f"«{t}» kelmadi; oxirgilari: {[m.get('t') for m in self.msgs[-5:]]}")


# ── sof mantiq ──


def test_points_league_outcome():
    assert bt.points_for(False, 0.1, False) == 0
    assert bt.points_for(True, 0.0, False) == 20
    assert bt.points_for(True, bt.QUESTION_SECONDS, False) == 10
    assert bt.points_for(True, bt.QUESTION_SECONDS / 2, True) == 30, "oxirgi savol ×2"
    assert bt.league(0)["id"] == "bronze" and bt.league(0)["next_at"] == 150
    assert bt.league(150)["title"] == "Kumush" and bt.league(799)["id"] == "gold"
    assert bt.league(5000)["id"] == "diamond" and bt.league(5000)["next_at"] == 0
    assert bt.outcome_of(50, 40, 9000, 1000) == 1
    assert bt.outcome_of(40, 40, 3000, 5000) == 1, "ball teng — tezrog'i yutadi"
    assert bt.outcome_of(40, 40, 3000, 3000) == 0
    assert bt.outcome_of(0, 0, 4000, 9000) == 0, "ikkalasi ham topolmadi — durang"


def test_questions_and_bot():
    rnd = random.Random(7)
    qs = bt.build_questions("A1", rnd)
    assert len(qs) == bt.QUESTIONS and len({q["key"] for q in qs}) == bt.QUESTIONS
    assert [q["type"] for q in qs[:4]] == ["ar_uz", "uz_ar", "ar_uz", "uz_ar"]
    for q in qs:
        assert q["answer"] in q["options"] and len(set(q["options"])) == len(q["options"]) == 4
    assert bt.bot_accuracy(0) == 0.6 and bt.bot_accuracy(10_000) == 0.85
    rights = sum(bt.bot_move(qs[0], 0.7, rnd)[1] == qs[0]["answer"] for _ in range(2000))
    assert 1250 < rights < 1550, "aniqlik ~70%"
    delay, _ = bt.bot_move(qs[0], 1.0, rnd)
    assert 0 < delay < bt.QUESTION_SECONDS


# ── jang oqimi (hub) ──


async def _users(session, make_user, *names):
    users = [await make_user(n) for n in names]
    await session.commit()
    return users


def _wrong(q: dict) -> str:
    return next(o for o in q["options"] if o != q["answer"])


@pytest.mark.asyncio
async def test_human_vs_human(session, make_user):
    ua, ub = await _users(session, make_user, "Ali", "Vali")
    a, b = FakeConn(), FakeConn()
    hub = bt.HUB
    await hub.connect(ua.id, a)
    await hub.connect(ub.id, b)
    assert await hub.join(ua.id, "Ali", 0, "A1", a) == "queued"
    assert await hub.join(ub.id, "Vali", 0, "A1", b) == "matched"
    ma, mb = await a.wait("matched"), await b.wait("matched")
    assert ma["opp"]["name"] == "Vali" and ma["opp"]["bot"] is False and mb["opp"]["name"] == "Ali"
    m = hub.matches[ua.id]
    for i in range(bt.QUESTIONS):
        qa, qb = await a.wait("q"), await b.wait("q")
        assert qa["i"] == qb["i"] == i and qa["options"] == qb["options"], "bir xil savol"
        assert "answer" not in qa, "to'g'ri javob oldindan yuborilmaydi"
        assert hub.answer(ua.id, i, m.questions[i]["answer"])
        assert not hub.answer(ua.id, i, m.questions[i]["answer"]), "ikkinchi marta qabul qilinmaydi"
        await b.wait("opp_answered")
        assert hub.answer(ub.id, i, _wrong(m.questions[i]))
        ra = await a.wait("round")
        assert ra["you"]["ok"] and ra["opp"]["ok"] is False and ra["answer"] == m.questions[i]["answer"]
    ea, eb = await a.wait("end"), await b.wait("end")
    assert ea["result"] == "win" and eb["result"] == "lose" and ea["reason"] == "done"
    assert ea["score"]["you"] > 200 and ea["correct"] == {"you": 10, "opp": 0}
    assert ea["delta"] == 20 and ea["points"] == 20 and ea["xp"] == bt.XP["win"]
    assert eb["delta"] == 0 and eb["xp"] == bt.XP["loss"], "ball 0 dan pastga tushmaydi"
    row = (await session.execute(select(Battle))).scalar_one()
    assert (row.p1_id, row.p2_id, row.winner, row.status) == (ua.id, ub.id, 1, "done")
    await session.refresh(ua)
    assert (ua.battle_points, ua.battle_games, ua.battle_wins) == (20, 1, 1)
    assert ua.id not in hub.matches and ub.id not in hub.matches


@pytest.mark.asyncio
async def test_bot_fallback_and_rewards(session, make_user):
    (ua,) = await _users(session, make_user, "Ali")
    a = FakeConn()
    hub = bt.HUB
    await hub.connect(ua.id, a)
    assert await hub.join(ua.id, "Ali", 0, "A0", a) == "queued"
    mt = await a.wait("matched")
    assert mt["opp"]["bot"] is True and mt["opp"]["name"] in bt.BOT_NAMES
    m = hub.matches[ua.id]
    for i in range(bt.QUESTIONS):
        await a.wait("q")
        hub.answer(ua.id, i, m.questions[i]["answer"])  # darhol va to'g'ri — bot tezroq bo'lolmaydi
        await a.wait("round")
    e = await a.wait("end")
    assert e["result"] == "win" and e["delta"] == bt.BOT_POINTS["win"] and e["xp"] == 4, "bot bilan — yarmi"
    row = (await session.execute(select(Battle))).scalar_one()
    assert row.p2_id is None and row.bot_name == mt["opp"]["name"] and row.level == "A0"
    xp = (await session.execute(select(XpLog))).scalar_one()
    assert xp.source == "battle:A0" and xp.amount == 4


@pytest.mark.asyncio
async def test_cancel_and_forfeit(session, make_user):
    ua, ub = await _users(session, make_user, "Ali", "Vali")
    a, b = FakeConn(), FakeConn()
    hub = bt.HUB
    await hub.connect(ua.id, a)
    await hub.connect(ub.id, b)
    assert await hub.join(ua.id, "Ali", 0, "B1", a) == "queued"
    assert hub.cancel(ua.id) and hub.in_queue("B1") == 0
    await asyncio.sleep(0.1)
    assert ua.id not in hub.matches, "bekor qilingach bot jangi boshlanmaydi"
    await hub.join(ua.id, "Ali", 0, "B1", a)
    await hub.join(ub.id, "Vali", 0, "B1", b)
    await a.wait("q")
    assert await hub.join(ua.id, "Ali", 0, "B1", a) == "busy"
    assert hub.leave(ua.id)
    ea, eb = await a.wait("end"), await b.wait("end")
    assert ea["result"] == "lose" and eb["result"] == "win" and eb["reason"] == "forfeit"
    row = (await session.execute(select(Battle))).scalar_one()
    assert row.status == "forfeit" and row.winner == 2


@pytest.mark.asyncio
async def test_reconnect_resumes_match(session, make_user):
    (ua,) = await _users(session, make_user, "Ali")
    a = FakeConn()
    hub = bt.HUB
    await hub.connect(ua.id, a)
    await hub.join(ua.id, "Ali", 0, "A1", a)
    await a.wait("q")
    hub.disconnect(ua.id, a)  # Telegram fonga o'tdi
    assert hub.matches[ua.id].players[0].conn is None
    a2 = FakeConn()
    assert await hub.connect(ua.id, a2) is True
    resume = await a2.wait("matched")
    assert resume["resume"] is True and resume["opp"]["bot"] is True
    hub.leave(ua.id)
    await a2.wait("end")


# ── WebSocket va REST ──


def _sign_init(tg_id: int, name: str, token: str) -> str:
    data = {"auth_date": str(int(time.time())), "query_id": "q1", "user": json.dumps({"id": tg_id, "first_name": name})}
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    data["hash"] = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    return urlencode(data)


class FakeWS:
    def __init__(self):
        self.inbox: asyncio.Queue = asyncio.Queue()
        self.conn = FakeConn()
        self.closed: int | None = None

    async def accept(self):
        pass

    async def receive_json(self):
        m = await self.inbox.get()
        if m is None:
            raise WebSocketDisconnect()
        return m

    async def send_json(self, m):
        await self.conn.send(m)

    async def close(self, code: int = 1000):
        self.closed = code


@pytest.mark.asyncio
async def test_ws_auth_join_play_and_limit(session, monkeypatch):
    from api.battle import battle_ws
    from config import settings

    token = "123456:TEST"
    monkeypatch.setattr(settings, "bot_token", token)
    monkeypatch.setattr(settings, "dev_auth", False)

    bad = FakeWS()
    task = asyncio.create_task(battle_ws(bad))
    await bad.inbox.put({"t": "auth", "init": "hash=yoq"})
    err = await bad.conn.wait("error")
    await task
    assert err["code"] == "auth" and bad.closed == 4003

    ws = FakeWS()
    task = asyncio.create_task(battle_ws(ws))
    await ws.inbox.put({"t": "auth", "init": _sign_init(555, "Sardor", token)})
    hello = await ws.conn.wait("hello")
    assert hello["online"] == 1
    await ws.inbox.put({"t": "ping"})
    assert (await ws.conn.wait("pong"))["online"] == 1
    await ws.inbox.put({"t": "join", "level": "A2"})
    assert (await ws.conn.wait("queued"))["level"] == "A2"
    assert (await ws.conn.wait("matched"))["opp"]["bot"] is True
    for i in range(bt.QUESTIONS):
        q = await ws.conn.wait("q")
        await ws.inbox.put({"t": "answer", "i": q["i"], "choice": q["options"][0]})
        await ws.conn.wait("round")
    end = await ws.conn.wait("end")
    assert end["result"] in ("win", "lose", "draw") and "points" in end
    user = (await session.execute(select(User).where(User.tg_id == 555))).scalar_one()
    assert user.name == "Sardor" and user.battle_games == 1

    # Kunlik limit (VIP'siz)
    for _ in range(bt.FREE_DAILY):
        session.add(Battle(level="A1", p1_id=user.id, winner=1, created_at=utcnow()))
    await session.commit()
    await ws.inbox.put({"t": "join", "level": "A1"})
    err = await ws.conn.wait("error")
    assert err["code"] == "limit" and str(bt.FREE_DAILY) in err["msg"]
    await ws.inbox.put(None)
    await task
    assert bt.HUB.online() == 0


@pytest.mark.asyncio
async def test_rest_me_top_history(session, make_user, monkeypatch):
    from db.session import get_session
    from main import app
    from services.telegram_auth import get_current_user

    ua, ub = await _users(session, make_user, "Ali", "Vali")
    ua.battle_points, ua.battle_games, ua.battle_wins = 170, 5, 4
    ub.battle_points, ub.battle_games, ub.battle_wins = 40, 3, 1
    session.add(Battle(level="A1", p1_id=ua.id, p2_id=ub.id, p1_score=180, p2_score=90, winner=1, p1_delta=20, p2_delta=-10))
    session.add(Battle(level="A0", p1_id=ua.id, bot_name="Zayd", p1_score=60, p2_score=120, winner=2, p1_delta=-5))
    await session.commit()

    async def _session():
        yield session

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: ua
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            me = (await c.get("/api/battle/me")).json()
            assert me["points"] == 170 and me["league"]["title"] == "Kumush" and me["rank"] == 1
            assert me["today"] == 2 and me["daily_limit"] == bt.FREE_DAILY and me["level"] in vocab.LEVELS
            top = (await c.get("/api/battle/top")).json()
            assert [x["name"] for x in top["items"]] == ["Ali", "Vali"] and top["me"]["rank"] == 1
            hist = (await c.get("/api/battle/history")).json()["items"]
            assert hist[0]["opp"] == "Zayd" and hist[0]["bot"] and hist[0]["result"] == "lose" and hist[0]["delta"] == -5
            assert hist[1]["opp"] == "Vali" and hist[1]["result"] == "win" and hist[1]["you"] == 180
    finally:
        app.dependency_overrides.clear()
