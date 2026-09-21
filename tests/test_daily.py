"""K17.7 — kunlik speaking savoli (bank, aylanish, XP, streak, API), sharhlar
(rozilik oqimi, paywall'ga chiqishi)."""

import json
import re
from datetime import date, datetime, timedelta

import httpx
import pytest

from db.models import AiUsage, DailySpeaking, XpLog, utcnow
from db.models import Testimonial as TRow
from services import billing, daily

HARAKAT = re.compile(r"[ً-ْ]")


# ── Savollar banki ──


def test_bank_shape():
    b = daily.bank()
    assert set(b) == set(daily.LEVELS)
    ids = []
    for lv, items in b.items():
        assert len(items) == 40, lv  # K21.4: 20 → 40
        for q in items:
            ids.append(q["id"])
            assert HARAKAT.search(q["ar"]), f"harakatsiz: {q['ar']}"
            assert q["translit"] and q["uz"]
            if lv in ("A0", "A1"):
                assert q["hint_uz"], f"{lv} savoliga javob shabloni kerak: {q['id']}"
    assert len(ids) == len(set(ids))


def test_question_rotates_by_day():
    d = date(2026, 9, 15)
    q1 = daily.question_for("A1", d)
    q2 = daily.question_for("A1", d + timedelta(days=1))
    assert q1["id"] != q2["id"]
    assert daily.question_for("A1", d + timedelta(days=20)) != q1, "40 ta savol — 20 kunda takrorlanmaydi"
    assert daily.question_for("A1", d + timedelta(days=40)) == q1, "40 kundan keyin aylanadi"
    assert len({daily.question_for("B2", d + timedelta(days=i))["id"] for i in range(40)}) == 40
    assert daily.question_for("zz", d)["id"].startswith("a0-"), "noma'lum daraja → A0"
    assert daily.question_by_id("b2-05")["ar"].startswith("مَا رَأْيُكَ")
    assert daily.question_by_id("yoq") is None


def test_xp_and_streak():
    assert daily.xp_for(0, False) == 5 and daily.xp_for(100, False) == 10
    assert daily.xp_for(85, True) == 5 + 4 + 2
    t = date(2026, 9, 15)
    iso = lambda n: (t - timedelta(days=n)).isoformat()  # noqa: E731
    assert daily.streak_of([], t) == (0, 0)
    assert daily.streak_of([iso(0)], t) == (1, 1)
    assert daily.streak_of([iso(1), iso(2), iso(3)], t) == (3, 3), "bugun hali yo'q — kechadan sanaladi"
    assert daily.streak_of([iso(2), iso(3)], t) == (0, 2), "kecha o'tkazib yuborilgan — uzildi"
    assert daily.streak_of([iso(0), iso(1), iso(5), iso(6), iso(7), iso(8)], t) == (2, 4)


# ── API ──


def _reply(score=80, fixed=""):
    return {
        "score": score,
        "feedback_uz": "Yaxshi javob! «فِي» dan keyin majrur.",
        "ideal_ar": "أَنَا مِنْ طَشْقَنْد.",
        "fixed_ar": fixed,
    }


def _envelope(obj: dict) -> dict:
    return {
        "id": "m",
        "type": "message",
        "role": "assistant",
        "model": "m",
        "content": [{"type": "text", "text": json.dumps(obj, ensure_ascii=False)}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 220, "output_tokens": 90},
    }


@pytest.fixture
def client(session, monkeypatch):
    import anthropic

    from config import settings
    from db.session import get_session
    from main import app
    from services import tts
    from services.telegram_auth import get_current_user

    monkeypatch.setattr(settings, "anthropic_api_key", "test")
    monkeypatch.setattr(tts, "schedule", lambda text, level: "")
    handlers: list = []

    def transport(request: httpx.Request):
        return handlers.pop(0)

    orig = anthropic.AsyncAnthropic

    class Patched(orig):
        def __init__(self, **kw):
            super().__init__(
                http_client=httpx.AsyncClient(transport=httpx.MockTransport(transport)), **kw
            )

    monkeypatch.setattr(anthropic, "AsyncAnthropic", Patched)

    async def _session():
        yield session

    state = {"user": None}
    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    c = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    try:
        yield c, handlers, state
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_daily_flow(client, session, make_user):
    from sqlalchemy import select

    c, handlers, state = client
    u = await make_user("Nodir")
    state["user"] = u

    r = await c.get("/api/v2/tutor/daily")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["level"] == "A0" and d["done"] is None and d["streak"] == 0 and d["ai"] is True
    assert d["question"]["id"].startswith("a0-") and d["question"]["translit"] and d["question"]["hint_uz"]
    assert d["day"] == daily._today().isoformat()

    handlers.append(httpx.Response(200, json=_envelope(_reply(85, "أَنَا مِنْ طَشْقَنْدَ"))))
    r = await c.post("/api/v2/tutor/daily/answer", json={"text": "🎤 انا من طشقند", "voice": True})
    assert r.status_code == 200, r.text
    a = r.json()
    assert a["result"]["score"] == 85 and a["xp"] == 5 + 4 + 2 and a["streak"] == 1
    assert a["result"]["fixed_ar"] == "أَنَا مِنْ طَشْقَنْدَ" and a["result"]["voice"] is True

    row = (await session.execute(select(DailySpeaking))).scalar_one()
    assert row.question_id == d["question"]["id"] and row.xp == 11 and row.day == d["day"]
    xp = (await session.execute(select(XpLog))).scalar_one()
    assert xp.amount == 11 and xp.source == f"daily:{d['day']}"
    assert (await session.execute(select(AiUsage))).scalar_one().feature == "daily"

    # Ikkinchi marta — yo'q
    r = await c.post("/api/v2/tutor/daily/answer", json={"text": "x", "voice": False})
    assert r.status_code == 409

    d2 = (await c.get("/api/v2/tutor/daily")).json()
    assert d2["done"]["score"] == 85 and d2["streak"] == 1 and d2["total"] == 1

    me = (await c.get("/api/me")).json()
    assert me["daily"] == {"done": True, "streak": 1, "best": 1, "total": 1}


@pytest.mark.asyncio
async def test_daily_streak_from_previous_days(client, session, make_user):
    c, _, state = client
    u = await make_user("Ali")
    state["user"] = u
    t = daily._today()
    for n in (1, 2, 3):
        session.add(DailySpeaking(user_id=u.id, day=(t - timedelta(days=n)).isoformat(), score=70, xp=8))
    await session.commit()
    d = (await c.get("/api/v2/tutor/daily")).json()
    assert d["done"] is None and d["streak"] == 3 and d["best"] == 3 and d["total"] == 3


@pytest.mark.asyncio
async def test_daily_without_key(client, make_user, monkeypatch):
    from config import settings

    c, _, state = client
    state["user"] = await make_user()
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    assert (await c.get("/api/v2/tutor/daily")).json()["ai"] is False
    r = await c.post("/api/v2/tutor/daily/answer", json={"text": "x", "voice": False})
    assert r.status_code == 503


# ── Sharhlar (rozilik) ──


@pytest.mark.asyncio
async def test_testimonials_merge_db_and_json(session, make_user, monkeypatch):
    u = await make_user("Shahnoza")
    session.add(TRow(user_id=u.id, feedback_id=1, name="Shahnoza K.", level="A2", text="Zo'r ilova"))
    session.add(TRow(user_id=u.id, feedback_id=2, name="X", level="A2", text="yashirin", published=0))
    await session.commit()
    monkeypatch.setattr(billing, "testimonials", lambda: [{"name": "Json", "text": "qo'lda", "level": "B1"}])
    out = await billing.all_testimonials(session)
    assert [t["name"] for t in out] == ["Shahnoza K.", "Json"]


class FakeSession:
    def __init__(self):
        self.calls = []

    async def __call__(self, bot, method, timeout=None):
        self.calls.append(method)
        return None

    async def close(self):
        pass


@pytest.fixture
def wired(session_factory, monkeypatch):
    from aiogram import Bot, Dispatcher

    from bot import admin as mod
    from bot.admin import router as admin_router
    from config import settings

    monkeypatch.setattr(mod, "SessionLocal", session_factory)
    monkeypatch.setattr(settings, "admin_id", 777001)
    bot = Bot(token="42:TESTTOKEN")
    bot.session = FakeSession()
    dp = Dispatcher()
    dp.include_router(admin_router)
    yield dp, bot
    admin_router._parent_router = None


def _msg(text: str, from_id: int):
    from aiogram.types import Chat, Message, User as TgUser

    chat = Chat(id=from_id, type="private")
    user = TgUser(id=from_id, is_bot=False, first_name="X")
    return Message(message_id=2, date=datetime.now(), chat=chat, from_user=user, text=text)


def _cb(data: str, from_id: int):
    from aiogram.types import CallbackQuery, Chat, Message, User as TgUser

    chat = Chat(id=from_id, type="private")
    user = TgUser(id=from_id, is_bot=False, first_name="X")
    msg = Message(message_id=5, date=datetime.now(), chat=chat, from_user=user, text="so'rov")
    return CallbackQuery(id="1", from_user=user, chat_instance="c", data=data, message=msg)


@pytest.mark.asyncio
async def test_sharh_consent_flow(session, make_user, wired):
    from aiogram.types import Update
    from sqlalchemy import select

    from services import feedback as fs

    dp, bot = wired
    author = await make_user(name="Zamira")
    fb = await fs.save(session, author.id, "Ilova juda foydali, ustoz tuzatadi", source="app")
    await session.commit()

    # Admin so'raydi → foydalanuvchiga rozilik xabari
    await dp.feed_update(bot, Update(update_id=1, message=_msg(f"/sharh {fb.id}", 777001)))
    sent = [m for m in bot.session.calls if type(m).__name__ == "SendMessage"]
    assert any(m.chat_id == author.tg_id and "maylimi" in m.text for m in sent)
    assert any(m.chat_id == 777001 and "Rozilik so'rovi yuborildi" in m.text for m in sent)

    # Begona bosdi — rad
    await dp.feed_update(bot, Update(update_id=2, callback_query=_cb(f"tst:ok:{fb.id}", 999)))
    assert (await session.execute(select(TRow))).scalar_one_or_none() is None

    # Egasi ✅ → sharh nashr, ikki marta bosilsa takrorlanmaydi
    await dp.feed_update(bot, Update(update_id=3, callback_query=_cb(f"tst:ok:{fb.id}", author.tg_id)))
    await dp.feed_update(bot, Update(update_id=4, callback_query=_cb(f"tst:ok:{fb.id}", author.tg_id)))
    rows = (await session.execute(select(TRow))).scalars().all()
    assert len(rows) == 1 and rows[0].name == "Zamira" and rows[0].text.startswith("Ilova juda")
    assert any(m.chat_id == 777001 and "rozi" in m.text for m in bot.session.calls if type(m).__name__ == "SendMessage")

    # Ro'yxat va yashirish
    await dp.feed_update(bot, Update(update_id=5, message=_msg("/sharhlar", 777001)))
    assert any("Zamira" in m.text for m in bot.session.calls if type(m).__name__ == "SendMessage")
    await dp.feed_update(bot, Update(update_id=6, message=_msg(f"/sharh off {rows[0].id}", 777001)))
    await session.refresh(rows[0])
    assert rows[0].published == 0


@pytest.mark.asyncio
async def test_sharh_non_admin_ignored(session, make_user, wired):
    from aiogram.types import Update

    dp, bot = wired
    await dp.feed_update(bot, Update(update_id=1, message=_msg("/sharh 1", 555)))
    assert not [m for m in bot.session.calls if type(m).__name__ == "SendMessage"]
