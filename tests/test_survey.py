"""K22.0 so'rovnoma: /sorov (test/hammaga), javob qabul qilish (matn, tugma, ovoz), XP bir marta, /fikrlar."""

from datetime import datetime

import pytest
from aiogram import Bot, Dispatcher
from aiogram.types import CallbackQuery, Chat, Message, Update, User as TgUser, Voice
from sqlalchemy import select

from db.models import Feedback, XpLog
from services import survey

ADMIN_ID = 777001


class FakeSession:
    def __init__(self):
        self.calls = []

    async def __call__(self, bot, method, timeout=None):
        self.calls.append(method)
        return None

    async def close(self):
        pass


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, **kw):
        self.sent.append((chat_id, text))


def _msg(text, from_id, voice=None):
    chat = Chat(id=from_id, type="private")
    u = TgUser(id=from_id, is_bot=False, first_name="X")
    return Message(message_id=2, date=datetime.now(), chat=chat, from_user=u, text=text, voice=voice)


def _cb(data, from_id):
    chat = Chat(id=from_id, type="private")
    u = TgUser(id=from_id, is_bot=False, first_name="X")
    m = Message(message_id=3, date=datetime.now(), chat=chat, from_user=u, text="so'rov")
    return CallbackQuery(id="1", from_user=u, chat_instance="c", data=data, message=m)


@pytest.fixture
def wired(session_factory, monkeypatch):
    from bot import admin as admin_mod, handlers as h_mod
    from bot.admin import router as admin_router
    from bot.handlers import router as bot_router
    from config import settings

    monkeypatch.setattr(admin_mod, "SessionLocal", session_factory)
    monkeypatch.setattr(h_mod, "SessionLocal", session_factory)
    monkeypatch.setattr(settings, "admin_id", ADMIN_ID)
    bot = Bot(token="42:TESTTOKEN")
    bot.session = FakeSession()
    dp = Dispatcher()
    dp.include_router(admin_router)
    dp.include_router(bot_router)
    yield dp, bot
    admin_router._parent_router = None
    bot_router._parent_router = None


async def _feed(wired, message=None, callback=None):
    dp, bot = wired
    upd = Update(update_id=1, message=message) if message else Update(update_id=1, callback_query=callback)
    await dp.feed_update(bot, upd)
    return bot.session.calls


def _texts(calls):
    return [getattr(c, "text", None) for c in calls if type(c).__name__ == "SendMessage"]


@pytest.mark.asyncio
async def test_record_saves_notifies_xp_once(session, make_user, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "admin_id", ADMIN_ID)
    u = await make_user("Zamira")
    u.survey_pending = 1
    bot = FakeBot()
    fb, xp = await survey.record(session, bot, u, "Speaking qiyin, lug'at zo'r")
    assert fb.source == "survey" and fb.context == "sorov" and xp == 10 and u.survey_pending == 0
    assert bot.sent and bot.sent[0][0] == ADMIN_ID and f"#F{fb.id}" in bot.sent[0][1]
    fb2, xp2 = await survey.record(session, bot, u, "yana bir fikr", kind="voice")
    assert xp2 == 0 and fb2.text.startswith("🎤 ")
    xps = (await session.execute(select(XpLog).where(XpLog.user_id == u.id, XpLog.source == "survey"))).scalars().all()
    assert [x.amount for x in xps] == [10]
    # Tugma javobi — XP yo'q
    v = await make_user("Vali")
    _, xp3 = await survey.record(session, bot, v, survey.OK_TEXT, kind="button")
    assert xp3 == 0
    rows = await survey.responses(session, 10)
    assert [r[1].name for r in rows] == ["Vali", "Zamira", "Zamira"]
    txt = survey.responses_text(rows, 3)
    assert "jami 3" in txt and "Speaking qiyin" in txt and f"#F{fb.id}" in txt
    assert survey.responses_text([], 0).startswith("📋")


@pytest.mark.asyncio
async def test_text_reply_only_when_pending(session, make_user, wired):
    u = await make_user("Nodir")
    tg = u.tg_id
    await session.commit()
    # pending yo'q — e'tiborsiz
    calls = await _feed(wired, message=_msg("shunchaki xabar", tg))
    assert _texts(calls) == []
    assert (await session.execute(select(Feedback))).scalars().all() == []
    # «Fikr yozish» tugmasi → pending → matn → saqlandi + rahmat + XP
    await _feed(wired, callback=_cb("sv:write", tg))
    await session.refresh(u)
    assert u.survey_pending == 1
    calls = await _feed(wired, message=_msg("Darslar zo'r, speaking qiyin", tg))
    texts = _texts(calls)
    assert any("Rahmat" in t and "+10 XP" in t for t in texts)
    fbs = (await session.execute(select(Feedback))).scalars().all()
    assert len(fbs) == 1 and fbs[0].text == "Darslar zo'r, speaking qiyin" and fbs[0].source == "survey"
    await session.refresh(u)
    assert u.survey_pending == 0
    # Buyruq matni fikr emas
    await _feed(wired, callback=_cb("sv:write", tg))
    await _feed(wired, message=_msg("/fikr", tg))
    assert len((await session.execute(select(Feedback))).scalars().all()) == 1


@pytest.mark.asyncio
async def test_ok_button_and_voice(session, make_user, wired, monkeypatch):
    from services import stt

    u = await make_user("Ali")
    tg = u.tg_id
    await session.commit()
    await _feed(wired, callback=_cb("sv:ok", tg))
    fbs = (await session.execute(select(Feedback))).scalars().all()
    assert len(fbs) == 1 and fbs[0].text == survey.OK_TEXT
    # Ovozli: STT o'zbekcha
    u.survey_pending = 1
    await session.commit()
    monkeypatch.setattr(stt, "available", lambda: True)

    async def fake_transcribe(audio, filename="", mime="", prompt="", lang="ar"):
        assert lang == "uz" and filename == "voice.ogg" and audio == b"OggS"
        return "Ustoz zo'r lekin ovoz tanimayapti"

    monkeypatch.setattr(stt, "transcribe", fake_transcribe)

    class F:
        file_path = "voice/1.ogg"

    class Buf:
        def read(self):
            return b"OggS"

    dp, bot = wired

    async def get_file(file_id):
        return F()

    async def download_file(path):
        return Buf()

    monkeypatch.setattr(bot, "get_file", get_file)
    monkeypatch.setattr(bot, "download_file", download_file)
    voice = Voice(file_id="v1", file_unique_id="u1", duration=12)
    calls = await _feed(wired, message=_msg(None, tg, voice=voice))
    assert any("Rahmat" in t for t in _texts(calls))
    fbs = (await session.execute(select(Feedback).order_by(Feedback.id))).scalars().all()
    assert fbs[-1].text == "🎤 Ustoz zo'r lekin ovoz tanimayapti"


@pytest.mark.asyncio
async def test_sorov_admin_commands(session, make_user, wired, monkeypatch):
    from bot import admin as admin_mod

    a = await make_user("A")
    b = await make_user("B")
    demo = await make_user("Demo", is_demo=1)
    await session.commit()
    # test — faqat adminga
    calls = await _feed(wired, message=_msg("/sorov test", ADMIN_ID))
    texts = _texts(calls)
    assert len(texts) == 2 and "fikringizni" in texts[0] and "Shunday ko'rinadi" in texts[1]
    for u in (a, b, demo):
        await session.refresh(u)
        assert u.survey_pending == 0
    # hammaga
    blasted = []

    async def fake_blast(bot, ids, text, **kw):
        blasted.append((sorted(ids), text, kw))
        return len(ids), 0

    monkeypatch.setattr(admin_mod, "_blast", fake_blast)
    calls = await _feed(wired, message=_msg("/sorov Salom! Fikringiz?", ADMIN_ID))
    assert blasted and blasted[0][0] == sorted([a.tg_id, b.tg_id]) and blasted[0][1] == "Salom! Fikringiz?"
    assert blasted[0][2]["reply_markup"].inline_keyboard[0][0].callback_data == "sv:write"
    for u in (a, b):
        await session.refresh(u)
        assert u.survey_pending == 1
    await session.refresh(demo)
    assert demo.survey_pending == 0
    assert any("Yuborildi: 2" in t for t in _texts(calls))
    # /fikrlar
    await survey.record(session, FakeBot(), a, "Yaxshi")
    calls = await _feed(wired, message=_msg("/fikrlar 5", ADMIN_ID))
    assert any("So'rov javoblari" in t and "Yaxshi" in t for t in _texts(calls))
    # admin emas — jim (calls yig'ilib boradi: yangi SendMessage bo'lmasin)
    before = len(_texts(calls))
    calls = await _feed(wired, message=_msg("/sorov", a.tg_id))
    assert len(_texts(calls)) == before
