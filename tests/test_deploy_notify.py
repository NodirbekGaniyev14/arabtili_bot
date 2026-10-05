"""«🔄 Bot yangilandi» xabari — har deployda emas, har DEPLOY_NOTIFY_EVERY (10) deployda bir marta (egasi 2026-10-05:
har deploydagi xabar sabab o'quvchilar botni bloklayapti)."""

import pytest

from config import settings
from db.models import Meta, User
from services import deploy_notify as dn


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, **kw):
        self.sent.append((chat_id, text))


async def _deploy(monkeypatch, version):
    monkeypatch.setattr(dn, "current_version", lambda: version)
    bot = FakeBot()
    await dn.notify_if_updated(bot)
    return bot.sent


@pytest.fixture
def users(session_factory, monkeypatch):
    monkeypatch.setattr(dn, "SessionLocal", session_factory)
    monkeypatch.setattr(settings, "deploy_notify_every", 10)

    async def make():
        async with session_factory() as s:
            s.add_all([User(tg_id=101, name="A"), User(tg_id=102, name="B", notify_off="news"),
                       User(tg_id=103, name="Demo", is_demo=1)])
            await s.commit()

    return make


@pytest.mark.asyncio
async def test_update_message_only_every_tenth_deploy(users, session_factory, monkeypatch):
    await users()
    assert await _deploy(monkeypatch, "v000") == [], "birinchi ishga tushish (yangi baza) — deploy emas"
    for i in range(1, 10):
        assert await _deploy(monkeypatch, f"v{i:03d}") == [], f"{i}-deploy — xabar yo'q"
    assert await _deploy(monkeypatch, "v009") == [], "versiya o'zgarmagan restart — hisoblanmaydi"
    sent = await _deploy(monkeypatch, "v010")
    assert [chat for chat, _ in sent] == [101], "10-deploy: faqat «yangiliklar» yoqilgan haqiqiy o'quvchiga"
    assert "Bot yangilandi" in sent[0][1]
    assert await _deploy(monkeypatch, "v011") == [], "hisoblagich qaytadan boshlanadi"
    async with session_factory() as s:
        assert await dn.notice_status(s) == (1, 10)
        assert (await s.get(Meta, dn.VERSION_KEY)).value == "v011"
        assert await dn.last_deploy_at(s) is not None, "deploy vaqti har deployda yoziladi"


@pytest.mark.asyncio
async def test_zero_disables_update_message(users, monkeypatch):
    await users()
    monkeypatch.setattr(settings, "deploy_notify_every", 0)
    for i in range(25):
        assert await _deploy(monkeypatch, f"z{i:03d}") == []


@pytest.mark.asyncio
async def test_diag_shows_next_update_message(users, session_factory, monkeypatch):
    import db.session as dbs
    from services import diag

    await users()
    monkeypatch.setattr(dbs, "SessionLocal", session_factory)
    for v in ("a", "b", "c", "d"):  # birinchisi — yangi baza, keyin 3 ta deploy
        await _deploy(monkeypatch, v)
    line = await diag.check_deploy_notice()
    assert line.startswith("✅") and "har 10 deployda" in line and "beri 3 ta deploy" in line and "keyingisi 7-deployda" in line
    monkeypatch.setattr(settings, "deploy_notify_every", 0)
    assert "o'chiq" in await diag.check_deploy_notice()
