"""K18.1 — taklif dasturi (havola, bog'lash, birinchi darsdan keyin VIP, limit,
/start ref, /taklif) va 2 kunlik VIP sinov (API, eslatmalar)."""

from datetime import datetime, timedelta

import httpx
import pytest

from db.models import User, utcnow
from services import billing, referral, vip_reminders as vr


class FakeBot:
    def __init__(self):
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id, text, **kw):
        self.sent.append((chat_id, text))


@pytest.fixture(autouse=True)
def _cfg(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "bot_username", "TestArabiy_bot")
    monkeypatch.setattr(settings, "webapp_url", "https://arabiy.example/app")


# ── Havola va bog'lash ──


def test_link_and_parse():
    u = User(tg_id=5000431126)
    assert referral.link_for(u) == "https://t.me/TestArabiy_bot?start=ref5000431126"
    assert "start%3Dref5000431126" in referral.share_url(u)
    assert referral.parse_start_arg("ref123") == 123
    assert referral.parse_start_arg("ref") is None
    assert referral.parse_start_arg("promo") is None
    assert referral.parse_start_arg("") is None


@pytest.mark.asyncio
async def test_attach_rules(session, make_user):
    ref = await make_user("Ref")
    new = await make_user("New")
    assert not await referral.attach(session, new, new.tg_id), "o'zini o'zi"
    assert not await referral.attach(session, new, 999_999), "yo'q taklifchi"
    assert await referral.attach(session, new, ref.tg_id)
    assert new.invited_by == ref.id
    other = await make_user("Other")
    assert not await referral.attach(session, new, other.tg_id), "ikkinchi marta bog'lanmaydi"
    assert new.invited_by == ref.id


@pytest.mark.asyncio
async def test_reward_once_and_cap(session, make_user, monkeypatch):
    ref = await make_user("Ref")
    new = await make_user("New", invited_by=1)
    new.invited_by = ref.id
    await session.commit()
    bot = FakeBot()

    r = await referral.on_lesson_passed(session, new, bot)
    assert r == {"days": referral.REF_DAYS, "referrer_paid": True}
    assert billing.vip_days_left(new) == referral.REF_DAYS
    assert billing.vip_days_left(ref) == referral.REF_DAYS
    assert new.ref_rewarded == 1
    assert {c for c, _ in bot.sent} == {new.tg_id, ref.tg_id}
    assert "3 kun VIP" in bot.sent[0][1]

    assert await referral.on_lesson_passed(session, new, bot) is None, "faqat bir marta"
    assert len(bot.sent) == 2

    # Limit: taklifchi allaqachon 10 ta mukofot olgan → faqat yangi o'quvchi oladi
    for i in range(referral.REF_MAX_REWARDS):
        await make_user(f"F{i}", invited_by=ref.id, ref_rewarded=1)
    await session.commit()
    late = await make_user("Late", invited_by=ref.id)
    before = ref.vip_until
    r = await referral.on_lesson_passed(session, late, None)
    assert r["referrer_paid"] is False and ref.vip_until == before
    assert billing.is_vip(late)

    st = await referral.stats(session, ref)
    assert st["invited"] == 12 and st["rewarded"] == 12
    assert st["days_earned"] == referral.REF_MAX_REWARDS * referral.REF_DAYS
    assert st["link"].endswith(f"ref{ref.tg_id}")


# ── Bot: /start ref, /taklif ──


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

    from bot import admin as amod
    from bot import handlers as hmod
    from bot.admin import router as admin_router
    from bot.handlers import router as user_router
    from config import settings

    monkeypatch.setattr(amod, "SessionLocal", session_factory)
    monkeypatch.setattr(hmod, "SessionLocal", session_factory)
    monkeypatch.setattr(settings, "admin_id", 777001)
    bot = Bot(token="42:TESTTOKEN")
    bot.session = FakeSession()
    dp = Dispatcher()
    dp.include_router(admin_router)
    dp.include_router(user_router)
    yield dp, bot
    admin_router._parent_router = None
    user_router._parent_router = None


def _msg(text: str, from_id: int, name="X", username=""):
    from aiogram.types import Chat, Message, User as TgUser

    chat = Chat(id=from_id, type="private")
    user = TgUser(id=from_id, is_bot=False, first_name=name, username=username or None)
    return Message(message_id=1, date=datetime.now(), chat=chat, from_user=user, text=text)


@pytest.mark.asyncio
async def test_start_ref_attaches_only_new_users(session, make_user, wired):
    from aiogram.types import Update
    from sqlalchemy import select

    dp, bot = wired
    ref = await make_user("Ref")
    await session.commit()

    await dp.feed_update(bot, Update(update_id=1, message=_msg(f"/start ref{ref.tg_id}", 424242, "Yangi", "yangi")))
    new = (await session.execute(select(User).where(User.tg_id == 424242))).scalar_one()
    assert new.invited_by == ref.id and new.name == "Yangi" and new.username == "yangi"
    sent = [m for m in bot.session.calls if type(m).__name__ == "SendMessage"]
    assert sent and "taklifi bilan keldingiz" in sent[-1].text

    # Mavjud foydalanuvchi havola bilan kirsa — bog'lanmaydi
    old = await make_user("Old")
    await session.commit()
    await dp.feed_update(bot, Update(update_id=2, message=_msg(f"/start ref{ref.tg_id}", old.tg_id)))
    await session.refresh(old)
    assert old.invited_by is None
    assert "taklifi bilan" not in [m for m in bot.session.calls if type(m).__name__ == "SendMessage"][-1].text

    # O'zini o'zi
    await dp.feed_update(bot, Update(update_id=3, message=_msg("/start ref515151", 515151)))
    me = (await session.execute(select(User).where(User.tg_id == 515151))).scalar_one()
    assert me.invited_by is None


@pytest.mark.asyncio
async def test_taklif_command_for_everyone(session, make_user, wired):
    from aiogram.types import Update

    dp, bot = wired
    u = await make_user("Zamira")
    await make_user("Friend", invited_by=u.id, ref_rewarded=1)
    await session.commit()
    await dp.feed_update(bot, Update(update_id=1, message=_msg("/taklif", u.tg_id)))
    sent = [m for m in bot.session.calls if type(m).__name__ == "SendMessage"]
    assert sent and sent[-1].chat_id == u.tg_id
    text = sent[-1].text
    assert f"start=ref{u.tg_id}" in text and "Taklif qilingan: <b>1</b>" in text and "3 kun" in text
    assert sent[-1].reply_markup.inline_keyboard[0][0].url.startswith("https://t.me/share/url")

    # Bazada yo'q foydalanuvchi ham oladi (yaratiladi)
    await dp.feed_update(bot, Update(update_id=2, message=_msg("/taklif", 909090, "Nov")))
    assert [m for m in bot.session.calls if type(m).__name__ == "SendMessage"][-1].chat_id == 909090


# ── API: dars tugadi → mukofot; sinov ──


@pytest.fixture
def client(session, monkeypatch):
    from db.session import get_session
    from main import app
    from services.telegram_auth import get_current_user

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
async def test_first_lesson_pays_referral(client, session, make_user):
    c, state, bot = client
    ref = await make_user("Ref")
    new = await make_user("New", invited_by=ref.id)
    await session.commit()
    state["user"] = new

    # O'tmagan dars — mukofot yo'q
    r = await c.post("/api/v2/lessons/a0-01/complete", json={"correct": 1, "total": 7})
    assert r.status_code == 200 and r.json()["referral_bonus"] is None
    assert not billing.is_vip(new)

    r = await c.post("/api/v2/lessons/a0-01/complete", json={"correct": 7, "total": 7})
    assert r.status_code == 200, r.text
    assert r.json()["referral_bonus"] == {"days": 3, "referrer_paid": True}
    await session.refresh(ref)
    assert billing.is_vip(new) and billing.is_vip(ref)
    assert len(bot.sent) == 2

    # Ikkinchi dars — yana yo'q
    r = await c.post("/api/v2/lessons/a0-02/complete", json={"correct": 7, "total": 7})
    assert r.json()["referral_bonus"] is None and len(bot.sent) == 2

    prof = (await c.get("/api/profile")).json()
    assert prof["referral"]["link"].endswith(f"ref{new.tg_id}") and prof["referral"]["invited"] == 0


@pytest.mark.asyncio
async def test_trial_once(client, session, make_user, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "anthropic_api_key", "k")
    c, state, _ = client
    u = await make_user("T")
    state["user"] = u

    info = (await c.get("/api/pay/info")).json()
    assert info["trial_available"] is True and info["trial_days"] == 2 and info["referral_days"] == 3
    assert (await c.get("/api/v2/tutor/topics")).json()["trial_available"] is True

    r = await c.post("/api/pay/trial")
    assert r.status_code == 200 and r.json()["days"] == 2
    await session.refresh(u)
    assert billing.is_vip(u) and u.trial_until == u.vip_until and referral.on_trial(u)
    assert (await c.get("/api/pay/info")).json()["trial_available"] is False
    assert (await c.get("/api/v2/tutor/topics")).json()["vip"] is True

    assert (await c.post("/api/pay/trial")).status_code == 409

    # VIP faol foydalanuvchiga sinov taklif qilinmaydi
    v = await make_user("V", vip_until=utcnow() + timedelta(days=10))
    state["user"] = v
    assert (await c.get("/api/pay/info")).json()["trial_available"] is False
    assert (await c.post("/api/pay/trial")).status_code == 409

    # Sinovdan keyin sotib olsa — davr uzayadi, endi sinov emas
    billing.grant(u, 30)
    assert not referral.on_trial(u)


@pytest.mark.asyncio
async def test_reminders_skip_trial_soon_and_use_trial_expired_text(session, make_user, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "pay_price_month", 40_000)
    noon = datetime(2026, 9, 15, 7, 0, 0)
    t = await make_user("Trial")
    t.vip_until = noon + timedelta(days=1)
    t.trial_until = t.vip_until
    paid = await make_user("Paid", vip_until=noon + timedelta(days=1))
    await session.commit()
    bot = FakeBot()
    r = await vr.process(session, bot, noon)
    assert r["soon"] == 1 and [c for c, _ in bot.sent] == [paid.tg_id], "sinovda «tugayapti» yo'q"

    t.vip_until = noon - timedelta(hours=1)
    t.trial_until = t.vip_until
    t.vip_notice = ""
    await session.commit()
    bot = FakeBot()
    r = await vr.process(session, bot, noon)
    assert r["expired"] == 1
    assert "sinov tugadi" in bot.sent[0][1] and "3 kun VIP bepul" in bot.sent[0][1]
