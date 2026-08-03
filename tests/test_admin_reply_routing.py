"""Admin javobi haqiqiy aiogram marshrutidan o'tadimi.

Bu yerda filtr sinaladi: fikr xabariga reply qilinganda handler ishga
tushsin, oddiy replylar esa boshqa handlerlarga tegmasin.
"""

from datetime import datetime

import pytest
from aiogram import Bot, Dispatcher
from aiogram.types import Chat, Message, Update, User as TgUser

from bot.admin import router as admin_router
from config import settings
from services import feedback as fs

ADMIN_ID = 777001
OTHER_ID = 777002


class FakeSession:
    """aiogram so'rovlarini tarmoqqa chiqarmasdan yig'ib boradi."""

    def __init__(self):
        self.calls = []

    async def __call__(self, bot, method, timeout=None):
        self.calls.append(method)
        return None

    async def close(self):
        pass


def _msg(text: str, from_id: int, reply_text: str | None = None) -> Message:
    chat = Chat(id=from_id, type="private")
    user = TgUser(id=from_id, is_bot=False, first_name="X")
    reply = (
        Message(
            message_id=1, date=datetime.now(), chat=chat, from_user=user, text=reply_text
        )
        if reply_text is not None
        else None
    )
    return Message(
        message_id=2,
        date=datetime.now(),
        chat=chat,
        from_user=user,
        text=text,
        reply_to_message=reply,
    )


@pytest.fixture
def wired(session_factory, monkeypatch):
    from bot import admin as mod

    monkeypatch.setattr(mod, "SessionLocal", session_factory)
    monkeypatch.setattr(settings, "admin_id", ADMIN_ID)

    bot = Bot(token="42:TESTTOKEN")
    bot.session = FakeSession()
    dp = Dispatcher()
    dp.include_router(admin_router)
    yield dp, bot
    # Router bitta Dispatcher'ga bog'lanadi — keyingi test uchun bo'shatamiz
    admin_router._parent_router = None


async def _feed(wired, message: Message):
    dp, bot = wired
    await dp.feed_update(bot, Update(update_id=1, message=message))
    return bot.session.calls


async def test_admin_reply_reaches_author(session, make_user, wired):
    user = await make_user(name="Zamira")
    fb = await fs.save(session, user.id, "ismim xato", source="app")

    calls = await _feed(
        wired, _msg("Profildan o'zgartiring", ADMIN_ID, f"💬 Yangi fikr #F{fb.id}\nsalom")
    )

    to_author = [c for c in calls if getattr(c, "chat_id", None) == user.tg_id]
    assert len(to_author) == 1, f"muallifga 1 ta xabar kutilgan: {calls}"
    assert "Arabiy jamoasi" in to_author[0].text
    assert "Profildan o'zgartiring" in to_author[0].text


async def test_non_admin_reply_sends_nothing(session, make_user, wired):
    user = await make_user()
    fb = await fs.save(session, user.id, "salom", source="app")

    calls = await _feed(wired, _msg("javob", OTHER_ID, f"#F{fb.id}"))
    assert calls == []


async def test_reply_works_when_tag_is_not_at_line_start(session, make_user, wired):
    """Haqiqiy xabar `💬 Yangi fikr #F12` ko'rinishida — yorliq matn ichida."""
    user = await make_user()
    fb = await fs.save(session, user.id, "salom", source="app")

    calls = await _feed(
        wired,
        _msg("javob", ADMIN_ID, fs.admin_notice(fb, user)),  # aynan real matn
    )
    assert [c.chat_id for c in calls if getattr(c, "chat_id", None) == user.tg_id]


async def test_reply_without_tag_is_ignored(session, make_user, wired):
    """Yorliqsiz replyga handler tegmasin — boshqa xabarlarni yutmaydi."""
    await make_user()
    calls = await _feed(wired, _msg("shunchaki javob", ADMIN_ID, "oddiy xabar"))
    assert calls == []


async def test_javob_command_works(session, make_user, wired):
    user = await make_user()
    fb = await fs.save(session, user.id, "savol", source="bot")

    calls = await _feed(wired, _msg(f"/javob {fb.id} mana javob", ADMIN_ID))
    to_author = [c for c in calls if getattr(c, "chat_id", None) == user.tg_id]
    assert len(to_author) == 1
    assert "mana javob" in to_author[0].text


async def test_javob_command_from_non_admin_ignored(session, make_user, wired):
    user = await make_user()
    fb = await fs.save(session, user.id, "savol", source="bot")

    calls = await _feed(wired, _msg(f"/javob {fb.id} salom", OTHER_ID))
    assert calls == []


async def test_javob_without_args_shows_help(session, wired):
    calls = await _feed(wired, _msg("/javob", ADMIN_ID))
    assert len(calls) == 1
    assert calls[0].chat_id == ADMIN_ID
    assert "Foydalanish" in calls[0].text


# ── /fikr: to'liq aylanma ──


@pytest.fixture
def wired_user(session_factory, monkeypatch):
    """Foydalanuvchi handlerlari (bot/handlers.py) uchun dispatcher."""
    from bot import handlers as mod

    monkeypatch.setattr(mod, "SessionLocal", session_factory)
    monkeypatch.setattr(settings, "admin_id", ADMIN_ID)

    bot = Bot(token="42:TESTTOKEN")
    bot.session = FakeSession()
    dp = Dispatcher()
    dp.include_router(mod.router)
    yield dp, bot
    mod.router._parent_router = None


async def test_fikr_command_saves_and_notifies_admin(wired_user, session_factory):
    calls = await _feed(wired_user, _msg("/fikr ismim xato yozilgan", OTHER_ID))

    to_admin = [c for c in calls if getattr(c, "chat_id", None) == ADMIN_ID]
    to_user = [c for c in calls if getattr(c, "chat_id", None) == OTHER_ID]
    assert len(to_admin) == 1, "adminga xabar bormadi"
    assert "#F1" in to_admin[0].text
    assert "ismim xato yozilgan" in to_admin[0].text
    assert to_user and "Rahmat" in to_user[0].text

    from sqlalchemy import select

    from db.models import Feedback

    async with session_factory() as s:
        rows = (await s.execute(select(Feedback))).scalars().all()
    assert len(rows) == 1
    assert rows[0].source == "bot"


async def test_fikr_then_reply_full_loop(wired_user, wired, session_factory):
    """Foydalanuvchi /fikr yozadi -> admin reply qiladi -> javob unga qaytadi."""
    admin_calls = await _feed(wired_user, _msg("/fikr savolim bor", OTHER_ID))
    notice = next(c for c in admin_calls if c.chat_id == ADMIN_ID).text

    calls = await _feed(wired, _msg("mana javob", ADMIN_ID, notice))
    back = [c for c in calls if getattr(c, "chat_id", None) == OTHER_ID]
    assert len(back) == 1
    assert "mana javob" in back[0].text
    assert "savolim bor" in back[0].text
    assert "Arabiy jamoasi" in back[0].text
