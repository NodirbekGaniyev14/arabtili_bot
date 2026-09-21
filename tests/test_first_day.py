"""K20.4 — yangi foydalanuvchi: tanishuv kartasi bayrog'i (/api/me), 2-kun bot xabari
(kecha reja tuzganlarga, bir marta, faollikka qarab matn)."""

from datetime import datetime, timedelta

import httpx
import pytest

from db.models import Plan, Progress, TutorTurn, XpLog
from services import first_day as fd


class FakeBot:
    def __init__(self):
        self.sent: list[tuple[int, str, object]] = []

    async def send_message(self, chat_id, text, reply_markup=None, **kw):
        self.sent.append((chat_id, text, reply_markup))


NOON = datetime(2026, 9, 20, 7, 0)  # 12:00 Toshkent, yakshanba


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "admin_id", 0)
    monkeypatch.setattr(settings, "webapp_url", "https://arabiy.example/app")
    monkeypatch.setattr(fd, "SEND_PAUSE", 0)


@pytest.mark.asyncio
async def test_intro_pending(session, make_user):
    now = datetime.utcnow()
    fresh = await make_user("Fresh", created_at=now - timedelta(hours=5))
    assert await fd.intro_pending(session, fresh, now) is True
    session.add(TutorTurn(user_id=fresh.id, session_key="s", mode="chat"))
    await session.flush()
    assert await fd.intro_pending(session, fresh, now) is False, "ustoz bilan gaplashgan"
    old = await make_user("Old", created_at=now - timedelta(days=10))
    assert await fd.intro_pending(session, old, now) is False


@pytest.mark.asyncio
async def test_day2_message_once(session, make_user):
    # Kecha (19.09 Toshkent) reja tuzganlar
    yday = NOON - timedelta(days=1)
    active = await make_user("Nodir", created_at=yday)
    session.add(Plan(user_id=active.id, level="A0", target_level="A1", target_date="2027-01-01", created_at=yday))
    session.add(XpLog(user_id=active.id, amount=10, source="lesson:a0-01", created_at=yday + timedelta(hours=1)))
    session.add(Progress(user_id=active.id, lesson_id="a0-01", passed=1, total=5, correct=5))
    session.add(TutorTurn(user_id=active.id, session_key="s", mode="chat", created_at=yday + timedelta(hours=2)))
    idle = await make_user("Idle", created_at=yday)
    session.add(Plan(user_id=idle.id, level="A0", target_level="A1", target_date="2027-01-01", created_at=yday + timedelta(hours=10)))
    today = await make_user("Today", created_at=NOON - timedelta(hours=1))
    session.add(Plan(user_id=today.id, level="A0", target_level="A1", target_date="2027-01-01", created_at=NOON - timedelta(hours=1)))
    older = await make_user("Older", created_at=NOON - timedelta(days=3))
    session.add(Plan(user_id=older.id, level="A0", target_level="A1", target_date="2027-01-01", created_at=NOON - timedelta(days=3)))
    demo = await make_user("Demo", is_demo=1, created_at=yday)
    session.add(Plan(user_id=demo.id, level="A0", target_level="A1", target_date="2027-01-01", created_at=yday))
    await session.commit()

    bot = FakeBot()
    assert await fd.process(session, bot, datetime(2026, 9, 20, 3, 0)) == {"sent": 0, "failed": 0}, "08:00 — erta"
    out = await fd.process(session, bot, NOON)
    assert out == {"sent": 2, "failed": 0}
    by = {c: (t, kb) for c, t, kb in bot.sent}
    assert set(by) == {active.tg_id, idle.tg_id}
    t, kb = by[active.tg_id]
    assert "ikkinchi kun" in t and "📖 1 dars" in t and "Jamal bilan 1 javob" in t and "zo'r boshlanish" in t
    assert "tanishuv suhbati" not in t and len(kb.inline_keyboard) == 1
    t, kb = by[idle.tg_id]
    assert "mashq hali boshlanmadi" in t and "tanishuv suhbati" in t
    assert kb.inline_keyboard[0][0].web_app.url.endswith("#tutor")
    assert active.day2_notice == 1 and idle.day2_notice == 1
    assert today.day2_notice == 0 and older.day2_notice == 0 and demo.day2_notice == 0
    # Takror — jim; ertaga «Today» oladi
    assert await fd.process(session, bot, NOON + timedelta(hours=2)) == {"sent": 0, "failed": 0}
    assert (await fd.process(session, bot, NOON + timedelta(days=1)))["sent"] == 1 and today.day2_notice == 1


@pytest.fixture
def client(session):
    from db.session import get_session
    from main import app
    from services.telegram_auth import get_current_user

    async def _session():
        yield session

    state = {"user": None}
    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    c = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    try:
        yield c, state
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_me_intro_flag(client, make_user):
    c, state = client
    state["user"] = await make_user("Fresh", created_at=datetime.utcnow())
    d = (await c.get("/api/me")).json()
    assert d["intro_pending"] is True and d["intro_topic"] == "tanishish"


@pytest.mark.asyncio
async def test_first_lesson_nudge_same_day_once(session, make_user):
    """K22.1: reja tuzilgan kuni 2 soat o'tib dars tugatmaganlarga bitta turtki, tugma to'g'ri darsga."""
    now = datetime(2026, 9, 20, 9, 0)  # 14:00 Toshkent
    three_h = now - timedelta(hours=3)
    idle = await make_user("Idle", created_at=three_h)
    session.add(Plan(user_id=idle.id, level="A0", target_level="A1", target_date="2027-01-01", created_at=three_h))
    a1 = await make_user("A1", created_at=three_h)
    session.add(Plan(user_id=a1.id, level="A1", target_level="A2", target_date="2027-01-01", start_lesson="a1-03", created_at=three_h))
    fresh = await make_user("Fresh", created_at=now - timedelta(hours=1))
    session.add(Plan(user_id=fresh.id, level="A0", target_level="A1", target_date="2027-01-01", created_at=now - timedelta(hours=1)))
    done = await make_user("Done", created_at=three_h)
    session.add(Plan(user_id=done.id, level="A0", target_level="A1", target_date="2027-01-01", created_at=three_h))
    session.add(Progress(user_id=done.id, lesson_id="a0-01", passed=1, total=5, correct=5))
    yday = await make_user("Yday", created_at=now - timedelta(days=1))
    session.add(Plan(user_id=yday.id, level="A0", target_level="A1", target_date="2027-01-01", created_at=now - timedelta(days=1)))
    await session.commit()

    bot = FakeBot()
    assert await fd.nudge_process(session, bot, datetime(2026, 9, 20, 18, 30)) == {"sent": 0, "failed": 0}, "23:30 — soat tashqarida"
    out = await fd.nudge_process(session, bot, now)
    assert out == {"sent": 2, "failed": 0}
    by = {c: (t, kb) for c, t, kb in bot.sent}
    assert set(by) == {idle.tg_id, a1.tg_id}
    t, kb = by[idle.tg_id]
    assert "birinchi qadam" in t and "Arab alifbosi" in t and "daqiqa" in t
    assert kb.inline_keyboard[0][0].web_app.url.endswith("#lesson=a0-01")
    assert by[a1.tg_id][1].inline_keyboard[0][0].web_app.url.endswith("#lesson=a1-03")
    assert idle.first_nudge == 1 and a1.first_nudge == 1
    assert fresh.first_nudge == 0 and done.first_nudge == 0 and yday.first_nudge == 0
    # Takror — jim; «Fresh» 2 soat o'tgach oladi
    assert await fd.nudge_process(session, bot, now + timedelta(minutes=20)) == {"sent": 0, "failed": 0}
    assert (await fd.nudge_process(session, bot, now + timedelta(hours=2)))["sent"] == 1 and fresh.first_nudge == 1
