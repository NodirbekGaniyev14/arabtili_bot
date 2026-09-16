"""K18.2 — sifat halqasi: 👍/👎 sessiya bahosi, adminga 👎 xabari, /ustoz da foiz."""

from datetime import timedelta

import httpx
import pytest

from db.models import TutorRating, TutorTurn, utcnow


class FakeBot:
    def __init__(self):
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id, text, **kw):
        self.sent.append((chat_id, text))


@pytest.fixture
def client(session, monkeypatch):
    from config import settings
    from db.session import get_session
    from main import app
    from services.telegram_auth import get_current_user

    monkeypatch.setattr(settings, "admin_id", 42)

    async def _session():
        yield session

    state = {"user": None}
    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    bot = FakeBot()
    app.state.bot = bot
    c = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    try:
        yield c, state, bot
    finally:
        app.dependency_overrides.clear()
        del app.state.bot


@pytest.mark.asyncio
async def test_rate_upsert_and_admin_alert(client, session, make_user):
    from sqlalchemy import select

    c, state, bot = client
    u = await make_user("Nodir", username="nodir")
    state["user"] = u
    for _ in range(3):
        session.add(TutorTurn(user_id=u.id, session_key="sess-abc-123", mode="chat"))
    await session.commit()

    r = await c.post(
        "/api/v2/tutor/rate",
        json={"session_key": "sess-abc-123", "mode": "chat", "topic": "oila", "good": True, "comment": ""},
    )
    assert r.status_code == 200 and r.json() == {"ok": True}
    row = (await session.execute(select(TutorRating))).scalar_one()
    assert row.good == 1 and row.topic == "oila" and row.level == "A0" and bot.sent == []

    # Xuddi shu sessiya 👎 + izoh → yangilanadi (ikkinchi qator emas), admin xabari
    r = await c.post(
        "/api/v2/tutor/rate",
        json={"session_key": "sess-abc-123", "mode": "chat", "topic": "oila", "good": False, "comment": "<juda sekin>"},
    )
    assert r.status_code == 200
    rows = (await session.execute(select(TutorRating))).scalars().all()
    assert len(rows) == 1 and rows[0].good == 0 and rows[0].comment == "<juda sekin>"
    assert len(bot.sent) == 1 and bot.sent[0][0] == 42
    text = bot.sent[0][1]
    assert "👎" in text and "oila" in text and "A0" in text and "3 javob" in text
    assert "&lt;juda sekin&gt;" in text and "@nodir" in text

    # 👎 izohsiz, birinchi marta — «izohsiz» xabar; qayta izohsiz — xabar yo'q
    await c.post("/api/v2/tutor/rate", json={"session_key": "mock-key-1", "mode": "mock", "topic": "shifokor", "good": False})
    assert len(bot.sent) == 2 and "izohsiz" in bot.sent[1][1] and "mock" in bot.sent[1][1]
    await c.post("/api/v2/tutor/rate", json={"session_key": "mock-key-1", "mode": "mock", "topic": "shifokor", "good": False})
    assert len(bot.sent) == 2

    # Yaroqsiz rejim / kalit
    assert (await c.post("/api/v2/tutor/rate", json={"session_key": "x y", "mode": "chat", "good": True})).status_code == 422
    assert (await c.post("/api/v2/tutor/rate", json={"session_key": "abcd", "mode": "exam", "good": True})).status_code == 422


@pytest.mark.asyncio
async def test_ustoz_report_shows_quality(session, make_user, monkeypatch):
    from config import settings
    from services import admin

    monkeypatch.setattr(settings, "anthropic_api_key", "k")
    u = await make_user("A")
    session.add(TutorRating(user_id=u.id, session_key="s1", mode="chat", topic="oila", good=1))
    session.add(TutorRating(user_id=u.id, session_key="s2", mode="mock", topic="shifokor", good=0, comment="baho qattiq"))
    session.add(TutorRating(user_id=u.id, session_key="s3", mode="daily", topic="a0-01", good=1))
    session.add(
        TutorRating(user_id=u.id, session_key="old", mode="chat", good=0, created_at=utcnow() - timedelta(days=40))
    )
    await session.commit()
    text = await admin.tutor_report(session)
    assert "Sifat (30 kun): 👍 <b>67%</b> (3 baho)" in text
    assert "👎 mock · shifokor: baho qattiq" in text
    assert "7 kun: 👍 67% (3)" in text


@pytest.mark.asyncio
async def test_ustoz_report_without_ratings(session):
    from services import admin

    assert "Sifat: hali baho yo'q" in await admin.tutor_report(session)
