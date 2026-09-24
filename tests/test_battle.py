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
    assert ma["opp"]["name"] == "Vali" and "bot" not in ma["opp"] and mb["opp"]["name"] == "Ali"
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
    assert "bot" not in mt["opp"] and mt["opp"]["name"] in bt.BOT_NAMES, "klient sun'iy raqibni bilmaydi"
    m = hub.matches[ua.id]
    assert m.players[1].bot is True
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
    assert resume["resume"] is True and "bot" not in resume["opp"] and resume["opp"]["name"] in bt.BOT_NAMES
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
    assert (await ws.conn.wait("matched"))["opp"]["name"] in bt.BOT_NAMES
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
            assert hist[0]["opp"] == "Zayd" and "bot" not in hist[0] and hist[0]["result"] == "lose" and hist[0]["delta"] == -5
            assert hist[1]["opp"] == "Vali" and hist[1]["result"] == "win" and hist[1]["you"] == 180
    finally:
        app.dependency_overrides.clear()


# ── K25.2: do'st xonasi, qayta jang, havola, nishonlar ──


class FakeBot:
    def __init__(self):
        self.sent: list[tuple[int, str, object]] = []

    async def send_message(self, chat_id, text, reply_markup=None, **kw):
        self.sent.append((chat_id, text, reply_markup))


async def _play_to_end(hub, pairs, answer_right=True):
    """pairs: [(user_id, FakeConn)] — hamma savolga javob, «end» gacha."""
    uid0 = pairs[0][0]
    m = hub.matches[uid0]
    for i in range(bt.QUESTIONS):
        for uid, c in pairs:
            await c.wait("q")
            q = m.questions[i]
            hub.answer(uid, i, q["answer"] if answer_right else _wrong(q))
        for _uid, c in pairs:
            await c.wait("round")
    ends = [await c.wait("end") for _uid, c in pairs]
    await asyncio.sleep(0.05)  # «end» yuborilgach jang ro'yxatdan o'chiriladi (match_done)
    return ends


@pytest.mark.asyncio
async def test_friend_room_flow_and_badges(session, make_user, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "bot_username", "TestBot")
    ua, ub, uc = await _users(session, make_user, "Ali", "Vali", "Sami")
    a, b, c = FakeConn(), FakeConn(), FakeConn()
    hub = bt.HUB
    for u, conn in ((ua, a), (ub, b), (uc, c)):
        await hub.connect(u.id, conn)
    room = hub.create_room(ua.id, "Ali", 0, ua.tg_id, "A1", a)
    assert room and len(room.code) == 6 and hub.room_of[ua.id] == room.code
    msg = hub._room_msg(room, "host")
    assert msg["link"] == f"https://t.me/TestBot?start=duel_{room.code}" and msg["guest"] is None
    assert (await hub.join_room(ua.id, "Ali", 0, ua.tg_id, room.code, a))[0] == "host", "mezbon o'z havolasini ochdi"
    assert (await hub.join_room(ub.id, "Vali", 0, ub.tg_id, "YOQ123", b))[0] == "not_found"
    status, _ = await hub.join_room(ub.id, "Vali", 0, ub.tg_id, room.code.lower(), b)
    assert status == "started" and room.code not in hub.rooms and ua.id not in hub.room_of
    ma = await a.wait("matched")
    assert ma["mode"] == "friend" and ma["opp"]["name"] == "Vali"
    assert (await hub.join_room(uc.id, "Sami", 0, uc.tg_id, room.code, c))[0] == "not_found", "xona yopilgan"
    ea, eb = await _play_to_end(hub, [(ua.id, a), (ub.id, b)])
    assert ea["rematch"] is True and eb["rematch"] is True
    row = (await session.execute(select(Battle))).scalar_one()
    assert row.mode == "friend"
    ids = {x["id"] for x in ea.get("new_badges", [])}
    assert {"battle_first", "battle_friend", "battle_perfect"} <= ids
    assert hub.last_opp[ua.id][0] == ub.id and hub.last_opp[ub.id][0] == ua.id


@pytest.mark.asyncio
async def test_host_absent_gets_bot_message(session, make_user):
    ua, ub = await _users(session, make_user, "Ali", "Vali")
    a, b = FakeConn(), FakeConn()
    hub = bt.HUB
    fake_bot = FakeBot()
    hub.bot = fake_bot
    await hub.connect(ua.id, a)
    room = hub.create_room(ua.id, "Ali", 0, ua.tg_id, "A0", a)
    hub.disconnect(ua.id, a)  # mezbon ilovani yopdi
    assert room.host_conn is None and room.code in hub.rooms
    await hub.connect(ub.id, b)
    status, _ = await hub.join_room(ub.id, "Vali", 0, ub.tg_id, room.code, b)
    assert status == "waiting"
    assert len(fake_bot.sent) == 1 and fake_bot.sent[0][0] == ua.tg_id and "Vali" in fake_bot.sent[0][1]
    # Ikkinchi marta xabar yo'q (bir marta)
    await hub.join_room(ub.id, "Vali", 0, ub.tg_id, room.code, b)
    assert len(fake_bot.sent) == 1
    # Mezbon qaytdi (ilova ochildi) — connect xonani tiklaydi va jang boshlanadi
    a2 = FakeConn()
    assert await hub.connect(ua.id, a2) is True
    assert (await a2.wait("matched"))["mode"] == "friend"
    await b.wait("matched")
    hub.leave(ua.id)
    await a2.wait("end")


@pytest.mark.asyncio
async def test_rematch_accept_decline_and_expiry(session, make_user, monkeypatch):
    ua, ub = await _users(session, make_user, "Ali", "Vali")
    a, b = FakeConn(), FakeConn()
    hub = bt.HUB
    await hub.connect(ua.id, a)
    await hub.connect(ub.id, b)
    assert (await hub.rematch(ua.id, "Ali", 0, ua.tg_id, a))[0] == "no_opponent"
    await hub.join(ua.id, "Ali", 0, "B1", a)
    await hub.join(ub.id, "Vali", 0, "B1", b)
    await _play_to_end(hub, [(ua.id, a), (ub.id, b)], answer_right=False)

    # Rad etish
    status, room = await hub.rematch(ua.id, "Ali", 0, ua.tg_id, a)
    assert status == "offered" and room.mode == "rematch" and room.guest_id == ub.id and room.level == "B1"
    offer = await b.wait("rematch_offer")
    assert offer["from"] == "Ali" and offer["code"] == room.code
    assert hub.decline(ub.id, room.code)
    closed = await a.wait("room_closed")
    assert closed["reason"] == "declined" and room.code not in hub.rooms

    # Qabul qilish
    status, room = await hub.rematch(ua.id, "Ali", 0, ua.tg_id, a)
    offer = await b.wait("rematch_offer")
    status, _ = await hub.join_room(ub.id, "Vali", 0, ub.tg_id, offer["code"], b)
    assert status == "started"
    assert (await a.wait("matched"))["mode"] == "rematch"
    await b.wait("matched")
    hub.leave(ub.id)
    await a.wait("end")
    await b.wait("end")
    await asyncio.sleep(0.05)
    rows = (await session.execute(select(Battle).order_by(Battle.id))).scalars().all()
    assert [r.mode for r in rows] == ["queue", "rematch"]

    # Ikkalasi bir vaqtda «qayta jang» bossa — darhol jang
    await hub.rematch(ua.id, "Ali", 0, ua.tg_id, a)
    status, _ = await hub.rematch(ub.id, "Vali", 0, ub.tg_id, b)
    assert status == "started"
    hub.leave(ua.id)
    await a.wait("end")
    await b.wait("end")
    await asyncio.sleep(0.05)

    # Muddati o'tgan xona
    monkeypatch.setattr(bt, "REMATCH_TTL", 0.01)
    st, room = await hub.rematch(ua.id, "Ali", 0, ua.tg_id, a)
    assert room is not None, (st, list(hub.matches), hub.last_opp.get(ua.id))
    await asyncio.sleep(0.05)
    assert (await hub.join_room(ub.id, "Vali", 0, ub.tg_id, room.code, b))[0] == "not_found"
    assert (await a.wait("room_closed"))["reason"] == "expired"


class FakeMessage:
    def __init__(self, tg_id: int, name: str, text: str):
        from types import SimpleNamespace

        self.from_user = SimpleNamespace(id=tg_id, first_name=name, username="")
        self.text = text
        self.answers: list[tuple[str, object]] = []

    async def answer(self, text, reply_markup=None, **kw):
        self.answers.append((text, reply_markup))


@pytest.mark.asyncio
async def test_start_duel_link(session, make_user, session_factory, monkeypatch):
    import bot.handlers as h
    from config import settings

    monkeypatch.setattr(h, "SessionLocal", session_factory)
    monkeypatch.setattr(settings, "webapp_url", "https://arabiy.example/app")
    (ua,) = await _users(session, make_user, "Ali")
    room = bt.HUB.create_room(ua.id, "Ali", 40, ua.tg_id, "A2", FakeConn())

    msg = FakeMessage(777001, "Yangi", f"/start duel_{room.code}")
    await h.cmd_start(msg)
    text, kb = msg.answers[-1]
    assert "Ali" in text and "Oktagon" in text and "A2" in text
    url = kb.inline_keyboard[0][0].web_app.url
    assert url.endswith(f"#duel={room.code}")
    new = (await session.execute(select(User).where(User.tg_id == 777001))).scalar_one()
    assert new.invited_by == ua.id, "do'st havolasi — referal ham"

    own = FakeMessage(ua.tg_id, "Ali", f"/start duel_{room.code}")
    await h.cmd_start(own)
    assert "sizning taklif" in own.answers[-1][0]

    old = FakeMessage(777002, "Boshqa", "/start duel_YOQ999")
    await h.cmd_start(old)
    text, kb = old.answers[-1]
    assert "muddati tugagan" in text and kb.inline_keyboard[0][0].web_app.url.endswith("#battle")


# ── K25.4: sun'iy raqib yashirin — o'zbekcha ism, «bot» belgisi yo'q, qayta jang ──


def test_bot_names_are_uzbek():
    assert len(bt.BOT_NAMES) >= 30 and len(set(bt.BOT_NAMES)) == len(bt.BOT_NAMES)
    for old in ("Zayd", "Layla", "Umar", "Maryam", "Yusuf", "Fotima", "Bilol", "Oysha", "Solih", "Hind"):
        assert old not in bt.BOT_NAMES
    assert {"Jasur", "Dilnoza", "Sardor", "Madina"} <= set(bt.BOT_NAMES)


@pytest.mark.asyncio
async def test_bot_never_named_like_user(session, make_user, monkeypatch):
    monkeypatch.setattr(bt, "BOT_NAMES", ["Jasur", "Dilnoza"])
    (ua,) = await _users(session, make_user, "Jasur")
    a = FakeConn()
    hub = bt.HUB
    await hub.connect(ua.id, a)
    await hub.join(ua.id, "Jasur", 0, "A0", a)
    assert (await a.wait("matched"))["opp"]["name"] == "Dilnoza"
    hub.leave(ua.id)
    await a.wait("end")


def _walk(x):
    if isinstance(x, dict):
        for k, v in x.items():
            yield str(k)
            yield from _walk(v)
    elif isinstance(x, (list, tuple)):
        for v in x:
            yield from _walk(v)
    else:
        yield str(x)


@pytest.mark.asyncio
async def test_bot_rematch_and_no_bot_word_to_client(session, make_user):
    (ua,) = await _users(session, make_user, "Ali")
    a = FakeConn()
    hub = bt.HUB
    await hub.connect(ua.id, a)
    await hub.join(ua.id, "Ali", 0, "A1", a)
    first = await a.wait("matched")
    name = first["opp"]["name"]
    m = hub.matches[ua.id]
    for i in range(bt.QUESTIONS):
        await a.wait("q")
        hub.answer(ua.id, i, _wrong(m.questions[i]))
        await a.wait("round")
    end = await a.wait("end")
    assert end["rematch"] is True, "sun'iy raqib bilan ham «Qayta jang» tugmasi"
    assert hub.last_opp[ua.id][0] is None and hub.last_opp[ua.id][2] == name

    # «Qayta jang»: odamdagidek taklif ekrani, keyin o'sha ism bilan jang
    status, room = await hub.rematch(ua.id, "Ali", 0, ua.tg_id, a)
    assert status == "offered" and room.mode == "rematch" and room.code not in hub.rooms
    msg = hub._room_msg(room, "host")
    assert msg["guest"]["name"] == name and msg["mode"] == "rematch"
    again = await a.wait("matched", timeout=3)
    assert again["opp"]["name"] == name and again["resume"] is False
    hub.leave(ua.id)
    await a.wait("end")

    # Taklifni bekor qilsa — jang boshlanmaydi
    await asyncio.sleep(0.05)
    status, _ = await hub.rematch(ua.id, "Ali", 0, ua.tg_id, a)
    assert status == "offered" and ua.id in hub.bot_rematch
    assert hub.leave_room(ua.id) is True and ua.id not in hub.bot_rematch
    await asyncio.sleep(bt.BOT_ACCEPT[1] * bt.QUESTION_SECONDS / 10 + 0.1)
    assert ua.id not in hub.matches

    # Klientga ketgan HECH bir xabarda «bot» kaliti yoki 🤖 yo'q
    for msg in a.msgs:
        for token in _walk(msg):
            assert token != "bot" and "🤖" not in token, msg

    # Bazada esa farq saqlanadi (admin statistikasi, ball jadvali)
    rows = (await session.execute(select(Battle).order_by(Battle.id))).scalars().all()
    assert [r.p2_id for r in rows] == [None, None] and {r.bot_name for r in rows} == {name}
    assert {r.mode for r in rows} == {"queue"}, "sun'iy raqib bilan qayta jang «do'st jangi» hisoblanmaydi"
