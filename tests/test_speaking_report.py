"""K18.4 — haftalik speaking hisoboti: statistika oynasi, matn (▲/▼, maslahat),
dushanba tarqatish (bir marta, faqat faollarga, jim qolganlarga turtki), /hisobot."""

from datetime import datetime, timedelta

import pytest

from db.models import (
    DailySpeaking,
    DrillResult,
    ListeningResult,
    MockResult,
    TutorMistake,
    TutorTurn,
    XpLog,
)
from services import speaking_report as sr


class FakeBot:
    def __init__(self):
        self.sent: list[tuple[int, str, object]] = []

    async def send_message(self, chat_id, text, reply_markup=None, **kw):
        self.sent.append((chat_id, text, reply_markup))


# Dushanba 2026-09-21 11:00 Toshkent = 06:00 UTC
MONDAY = datetime(2026, 9, 21, 6, 0)
THIS = sr.week_start_utc(MONDAY)  # 2026-09-20 19:00 UTC
PREV = THIS - timedelta(days=7)
PREV2 = PREV - timedelta(days=7)


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "admin_id", 0)
    monkeypatch.setattr(settings, "webapp_url", "https://arabiy.example/app")
    monkeypatch.setattr(sr, "SEND_PAUSE", 0)


def test_week_helpers():
    assert THIS == datetime(2026, 9, 20, 19, 0) and THIS.weekday() == 6  # dushanba 00:00 Toshkent
    assert sr.week_key(PREV) == "2026-09-14"
    assert sr.week_label(PREV) == "14.09 — 20.09.2026"
    assert sr.week_label(THIS, MONDAY) == "21.09 — 21.09.2026"
    # Yakshanba kechqurun 23:30 Toshkent hali o'sha hafta
    assert sr.week_start_utc(datetime(2026, 9, 20, 18, 30)) == PREV
    assert sr._due(MONDAY) and not sr._due(MONDAY + timedelta(days=1))
    assert not sr._due(datetime(2026, 9, 21, 3, 0)), "08:00 — erta"
    assert not sr._due(datetime(2026, 9, 21, 16, 0)), "21:00 — kech"


async def _fill(session, uid: int):
    """O'tgan hafta (PREV) to'la faollik, undan oldingi hafta ozroq."""
    t = PREV + timedelta(days=1, hours=8)
    for i in range(4):
        session.add(TutorTurn(user_id=uid, session_key="s1", topic="oila", level="A1", ok=int(i < 3),
                              voice=int(i < 2), mode="chat", created_at=t + timedelta(hours=i)))
    session.add(TutorTurn(user_id=uid, session_key="m1", mode="mock", score=80, created_at=t))  # sanalmaydi
    session.add(MockResult(user_id=uid, mock_id="shifokor", level="A2", score=78, xp=39, session_key="m1", created_at=t))
    for i, sc in enumerate((60, 70, 80)):
        session.add(DailySpeaking(user_id=uid, day=f"2026-09-{15 + i}", score=sc, voice=int(i == 0), xp=8))
    session.add(DrillResult(user_id=uid, topic="oila", level="A1", score=82, count=10, xp=8, created_at=t))
    session.add(ListeningResult(user_id=uid, topic="oila", kind="choice", level="A1", score=90, count=10, xp=9, created_at=t))
    session.add(TutorMistake(user_id=uid, kind="chat", topic="oila", said_ar="a", fixed_ar="b", created_at=t))
    session.add(TutorMistake(user_id=uid, kind="mock", topic="shifokor", said_ar="c", fixed_ar="d", created_at=t))
    for src, amt in (("tutor:s1", 20), ("tutor:m1", 39), ("drill:k", 8), ("listen:k", 9), ("daily:2026-09-15", 8), ("lesson:a1-01", 50)):
        session.add(XpLog(user_id=uid, amount=amt, source=src, created_at=t))
    # Undan oldingi hafta
    t2 = PREV2 + timedelta(days=2)
    session.add(TutorTurn(user_id=uid, session_key="s0", mode="chat", ok=1, voice=1, created_at=t2))
    session.add(TutorTurn(user_id=uid, session_key="s0", mode="chat", ok=0, voice=0, created_at=t2))
    session.add(MockResult(user_id=uid, mock_id="shifokor", level="A2", score=70, session_key="m0", created_at=t2))
    session.add(DailySpeaking(user_id=uid, day="2026-09-09", score=50, xp=7))
    session.add(XpLog(user_id=uid, amount=30, source="tutor:s0", created_at=t2))
    await session.flush()


@pytest.mark.asyncio
async def test_stats_window_and_text(session, make_user):
    u = await make_user("Nodir")
    await _fill(session, u.id)

    cur = await sr.stats(session, u.id, PREV, THIS)
    assert cur["chat"] == 4 and cur["chat_voice"] == 2 and cur["chat_ok"] == 3
    assert cur["mock_n"] == 1 and cur["mock_best"] == 78 and cur["mock_best_title"].startswith("Shifokor")
    assert cur["daily_days"] == 3 and cur["daily_avg"] == 70 and cur["daily_voice"] == 1
    assert cur["drill_n"] == 1 and cur["drill_sent"] == 10 and cur["drill_avg"] == 82
    assert cur["listen_n"] == 1 and cur["listen_avg"] == 90
    assert cur["mistakes_new"] == 2
    assert cur["xp"] == 20 + 39 + 8 + 9 + 8, "dars XP speaking'ga kirmaydi"
    assert cur["total"] == 4 + 1 + 3 + 1 + 1

    prev = await sr.stats(session, u.id, PREV2, PREV)
    assert prev["chat"] == 2 and prev["mock_best"] == 70 and prev["daily_days"] == 1 and prev["xp"] == 30
    assert (await sr.stats(session, u.id, THIS, MONDAY))["total"] == 0

    ctx = await sr.context(session, u, MONDAY)
    assert ctx["mistakes_open"] == 2 and ctx["streak"] == 0 and ctx["vip"] is False

    text = sr.render(u, cur, prev, sr.week_label(PREV), ctx)
    assert "Haftalik speaking hisoboti" in text and "14.09 — 20.09.2026" in text
    assert "💬 Suhbat: <b>4</b> javob ▲ 2 · 🎤 2 ovozli · xatosiz 75%" in text
    assert "eng yaxshi <b>Shifokor / hamshira 78%</b> ▲ 8" in text
    assert "🎙 Kunlik savol: <b>3/7</b> kun · o'rtacha 70% ▲ 20" in text and "streak" not in text.split("🎙 Kunlik")[1].split("\n")[0]
    assert "🎤 Talaffuz: 1 mashq · 10 jumla · o'rtacha 82%" in text
    assert "🎧 Tinglash: 1 mashq · o'rtacha 90%" in text
    assert "📒 Daftar: +2 yangi xato · jami 2 ta kutmoqda" in text
    assert "⭐ Speaking XP: <b>84</b> (o'tgan hafta 30 ▲ 54)" in text
    assert "💡 🎙 Kunlik savolni 4 kun o'tkazib yubordingiz" in text


def test_tips():
    from db.models import User

    base = dict(sr.EMPTY)
    ctx = {"mistakes_open": 0, "streak": 0, "vip": False}
    assert "Kunlik savol bepul" in sr.tip(base, ctx)
    full = {**base, "daily_days": 7, "chat": 4, "chat_voice": 1}
    assert "Daftarda 5 ta jumla" in sr.tip(full, {**ctx, "mistakes_open": 5})
    assert "Ko'proq ovoz" in sr.tip(full, ctx)
    voiced = {**full, "chat_voice": 4}
    assert "Mock imtihon" in sr.tip(voiced, {**ctx, "vip": True})
    assert "Talaffuz va 🎧 tinglash" in sr.tip(voiced, ctx)
    done = {**voiced, "drill_n": 1}
    assert "shu ruhda davom eting" in sr.tip(done, ctx)
    assert "qolgan 3 kunida" in sr.tip({**done, "daily_days": 2}, ctx, current_week=True, days_left=3)
    # Joriy haftada «o'tkazib yubordingiz» yo'q (hafta tugamagan)
    assert "o'tkazib" not in sr.tip({**voiced, "daily_days": 2}, ctx, current_week=True)

    u = User(tg_id=1, name="")
    empty = sr.render(u, base, {**base, "total": 5}, "x", ctx)
    assert "do'stim, bu hafta speaking mashqi bo'lmadi" in empty and "O'tgan hafta 5 ta mashq" in empty
    assert "hali speaking mashqi yo'q" in sr.render(u, base, base, "x", ctx, current_week=True)


@pytest.mark.asyncio
async def test_process_monday_once(session, make_user, monkeypatch):
    from config import settings

    active = await make_user("Nodir")
    await _fill(session, active.id)
    quiet = await make_user("Far")  # faqat 2 hafta oldin faol → turtki
    session.add(TutorTurn(user_id=quiet.id, session_key="q", mode="chat", created_at=PREV2 + timedelta(days=1)))
    idle = await make_user("Idle")  # umuman faol emas → xabar yo'q
    demo = await make_user("Demo", is_demo=1)
    session.add(DrillResult(user_id=demo.id, topic="oila", score=50, count=5, created_at=PREV + timedelta(days=1)))
    old = await make_user("Old")  # 3 hafta oldin — ro'yxatga kirmaydi
    session.add(TutorTurn(user_id=old.id, session_key="o", mode="chat", created_at=PREV2 - timedelta(days=2)))
    await session.commit()
    monkeypatch.setattr(settings, "admin_id", 999)

    bot = FakeBot()
    assert await sr.process(session, bot, MONDAY + timedelta(days=1)) == {"sent": 0, "nudged": 0, "failed": 0}
    assert bot.sent == []

    out = await sr.process(session, bot, MONDAY)
    assert out == {"sent": 1, "nudged": 1, "failed": 0}
    by_id = {chat_id: (text, kb) for chat_id, text, kb in bot.sent}
    assert set(by_id) == {active.tg_id, quiet.tg_id, 999}
    text, kb = by_id[active.tg_id]
    assert "14.09 — 20.09.2026" in text and "<b>4</b> javob" in text
    assert kb is not None and kb.inline_keyboard[0][0].web_app.url.endswith("#tutor")
    assert "bu hafta speaking mashqi bo'lmadi" in by_id[quiet.tg_id][0] and "O'tgan hafta 1 ta mashq" in by_id[quiet.tg_id][0]
    assert "1 ta hisobot, 1 ta turtki" in by_id[999][0]
    assert active.speak_report_key == "2026-09-14" and quiet.speak_report_key == "2026-09-14"
    assert idle.speak_report_key == "" and demo.speak_report_key == "" and old.speak_report_key == ""

    # Takror (o'sha hafta) — jim; keyingi dushanba — yana (endi Nodir jim qolgan → turtki)
    bot.sent.clear()
    assert await sr.process(session, bot, MONDAY + timedelta(hours=3)) == {"sent": 0, "nudged": 0, "failed": 0}
    out = await sr.process(session, bot, MONDAY + timedelta(days=7))
    assert out["sent"] == 0 and out["nudged"] == 1 and active.speak_report_key == "2026-09-21"


@pytest.mark.asyncio
async def test_send_failure_marks_and_continues(session, make_user):
    a = await make_user("A")
    b = await make_user("B")
    for u in (a, b):
        session.add(DrillResult(user_id=u.id, topic="oila", score=60, count=5, created_at=PREV + timedelta(days=2)))
    await session.commit()

    class Bot(FakeBot):
        async def send_message(self, chat_id, text, reply_markup=None, **kw):
            if chat_id == a.tg_id:
                raise RuntimeError("blocked")
            await super().send_message(chat_id, text, reply_markup)

    bot = Bot()
    assert await sr.process(session, bot, MONDAY) == {"sent": 1, "nudged": 0, "failed": 1}
    assert [c for c, _, _ in bot.sent] == [b.tg_id]
    assert a.speak_report_key == "2026-09-14", "yetmasa ham qayta urinmaymiz"


@pytest.mark.asyncio
async def test_current_text(session, make_user):
    u = await make_user("Nodir")
    wed = THIS + timedelta(days=2, hours=7)  # chorshanba 12:00 Toshkent
    session.add(DailySpeaking(user_id=u.id, day="2026-09-21", score=60, xp=8))
    session.add(DailySpeaking(user_id=u.id, day="2026-09-23", score=80, xp=9))
    session.add(DrillResult(user_id=u.id, topic="oila", score=75, count=8, created_at=wed - timedelta(hours=1)))
    session.add(DrillResult(user_id=u.id, topic="oila", score=55, count=8, created_at=PREV + timedelta(days=3)))  # o'tgan hafta
    await session.flush()
    text = await sr.current_text(session, u, wed)
    assert "Speaking — joriy hafta" in text and "21.09 — 23.09.2026" in text
    assert "🎙 Kunlik savol: <b>2/7</b> kun · o'rtacha 70%" in text and "🔥 streak 2" not in text
    assert "🎤 Talaffuz: 1 mashq · 8 jumla · o'rtacha 75% ▲ 20" in text
    assert "qolgan 4 kunida" in text


class FakeSession:
    def __init__(self):
        self.calls = []

    async def __call__(self, bot, method, timeout=None):
        self.calls.append(method)
        return None

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_hisobot_command(session_factory, monkeypatch):
    from aiogram import Bot, Dispatcher
    from aiogram.types import Chat, Message, Update, User as TgUser

    from bot import handlers as mod
    from bot.handlers import router
    from db.models import User

    monkeypatch.setattr(mod, "SessionLocal", session_factory)
    async with session_factory() as s:
        s.add(User(tg_id=4242, name="Nodir"))
        await s.commit()

    bot = Bot(token="42:TESTTOKEN")
    bot.session = FakeSession()
    dp = Dispatcher()
    dp.include_router(router)
    try:
        def msg(text, uid):
            chat = Chat(id=uid, type="private")
            return Message(message_id=1, date=datetime.now(), chat=chat,
                           from_user=TgUser(id=uid, is_bot=False, first_name="N"), text=text)

        await dp.feed_update(bot, Update(update_id=1, message=msg("/hisobot", 4242)))
        m = bot.session.calls[-1]
        assert type(m).__name__ == "SendMessage" and m.parse_mode == "HTML"
        assert "Speaking — joriy hafta" in m.text and "hali speaking mashqi yo'q" in m.text
        assert m.reply_markup.inline_keyboard[0][0].web_app.url.endswith("#tutor")

        await dp.feed_update(bot, Update(update_id=2, message=msg("/hisobot", 5)))
        assert "/start" in bot.session.calls[-1].text
    finally:
        router._parent_router = None
