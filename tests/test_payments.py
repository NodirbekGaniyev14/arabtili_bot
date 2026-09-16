"""K18.5 — avto to'lov (Telegram Payments: Payme/Click): payload, invoice, pre-checkout
tekshiruvi, successful_payment → VIP (takror update jim), API, bot router."""

from datetime import datetime, timedelta

import httpx
import pytest
from aiogram.types import SuccessfulPayment
from sqlalchemy import select

from db.models import PaymentRequest, User
from services import billing, payments


class FakeBot:
    def __init__(self):
        self.sent: list[tuple[int, str]] = []
        self.invoices: list[dict] = []

    async def send_message(self, chat_id, text, **kw):
        self.sent.append((chat_id, text))

    async def create_invoice_link(self, **kw):
        self.invoices.append(kw)
        return "https://t.me/$test_invoice"


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "admin_id", 0)
    monkeypatch.setattr(settings, "pay_provider_token", "")
    monkeypatch.setattr(settings, "pay_provider_name", "Payme")
    monkeypatch.setattr(settings, "pay_price_month", 40_000)
    monkeypatch.setattr(settings, "pay_price_3month", 100_000)
    monkeypatch.setattr(settings, "pay_old_price_month", 90_000)


def _enable(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "pay_provider_token", "123:TEST:token")
    monkeypatch.setattr(settings, "bot_token", "42:TESTTOKEN")


def _sp(payload: str, total: int, charge="ch1", currency="UZS") -> SuccessfulPayment:
    return SuccessfulPayment(
        currency=currency, total_amount=total, invoice_payload=payload,
        telegram_payment_charge_id=charge, provider_payment_charge_id="prov-" + charge,
    )


def test_payload_roundtrip():
    u = User(id=12, tg_id=1)
    assert payments.payload(u, "1oy", 40_000) == "vip:1oy:12:40000"
    assert payments.parse_payload("vip:3oy:12:100000") == ("3oy", 12, 100_000)
    for bad in ("", "vip:1oy:12", "x:1oy:12:1", "vip:9oy:12:1", "vip:1oy:a:1", "vip:1oy:12:1:2"):
        assert payments.parse_payload(bad) is None, bad
    assert not payments.enabled()


@pytest.mark.asyncio
async def test_invoice_link(session, make_user, monkeypatch):
    u = await make_user("Nodir", paywall_seen_at=datetime.utcnow())  # chegirma taymeri yurmoqda
    bot = FakeBot()
    with pytest.raises(ValueError):
        await payments.invoice_link(bot, u, "1oy")  # token yo'q
    _enable(monkeypatch)
    assert payments.enabled()
    url, amount = await payments.invoice_link(bot, u, "1oy")
    assert url.startswith("https://t.me/$") and amount == 40_000
    inv = bot.invoices[0]
    assert inv["currency"] == "UZS" and inv["provider_token"] == "123:TEST:token"
    assert inv["prices"][0].amount == 4_000_000, "tiyin = so'm × 100"
    assert inv["payload"] == f"vip:1oy:{u.id}:40000" and "1 oylik VIP" in inv["title"]
    # Chegirma taymeri tugagan → eski narx
    u.paywall_seen_at = datetime.utcnow() - timedelta(days=3)
    _url, amount = await payments.invoice_link(bot, u, "3oy")
    assert amount == billing.plan_price("3oy", False) and bot.invoices[-1]["payload"].endswith(f":{amount}")


@pytest.mark.asyncio
async def test_validate(session, make_user):
    u = await make_user("Nodir")
    ok = f"vip:1oy:{u.id}:40000"
    assert await payments.validate(session, u.tg_id, ok, "UZS", 4_000_000) == ""
    assert "eskirgan" in await payments.validate(session, u.tg_id, "vip:1oy:x", "UZS", 4_000_000)
    assert "Summa" in await payments.validate(session, u.tg_id, ok, "UZS", 3_000_000)
    assert "Summa" in await payments.validate(session, u.tg_id, ok, "USD", 4_000_000)
    assert "Hisob" in await payments.validate(session, u.tg_id + 1, ok, "UZS", 4_000_000)
    assert "Hisob" in await payments.validate(session, u.tg_id, f"vip:1oy:{u.id + 99}:40000", "UZS", 4_000_000)


@pytest.mark.asyncio
async def test_on_success_grants_once(session, make_user, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "admin_id", 999)
    u = await make_user("Nodir", username="nodir")
    bot = FakeBot()
    now = datetime(2026, 9, 16, 10, 0)
    req = await payments.on_success(session, bot, u.tg_id, _sp(f"vip:1oy:{u.id}:40000", 4_000_000), now)
    assert req is not None and req.status == "approved" and req.provider == "telegram"
    assert req.amount == 40_000 and req.days == 30 and req.charge_id == "ch1" and req.provider_charge_id == "prov-ch1"
    assert billing.is_vip(u) and (u.vip_until - datetime.utcnow()).days >= 29
    assert [c for c, _ in bot.sent] == [u.tg_id, 999]
    assert "VIP yoqildi" in bot.sent[0][1]
    assert "Avto to'lov #" in bot.sent[1][1] and "@nodir" in bot.sent[1][1] and "40 000" in bot.sent[1][1]

    # Takror update (bir xil charge_id) — jim, VIP uzaymaydi
    before = u.vip_until
    assert await payments.on_success(session, bot, u.tg_id, _sp(f"vip:1oy:{u.id}:40000", 4_000_000), now) is None
    assert u.vip_until == before and len(bot.sent) == 2
    assert len((await session.execute(select(PaymentRequest))).scalars().all()) == 1

    # Ikkinchi to'lov (3 oy) — uzaytiradi
    await payments.on_success(session, bot, u.tg_id, _sp(f"vip:3oy:{u.id}:100000", 10_000_000, charge="ch2"), now)
    assert u.vip_until == before + timedelta(days=90)

    # Payload tushunarsiz — VIP yo'q, admin ogohlantiriladi
    bot.sent.clear()
    assert await payments.on_success(session, bot, u.tg_id, _sp("garbage", 4_000_000, charge="ch3"), now) is None
    assert bot.sent[0][0] == 999 and "tushunilmadi" in bot.sent[0][1]


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
        yield c, state, app
    finally:
        app.dependency_overrides.clear()
        if hasattr(app.state, "bot"):
            del app.state.bot


@pytest.mark.asyncio
async def test_invoice_api(client, make_user, monkeypatch):
    c, state, app = client
    state["user"] = await make_user("Nodir", paywall_seen_at=datetime.utcnow())
    info = (await c.get("/api/pay/info")).json()
    assert info["auto_pay"] is False and info["provider_name"] == "Payme"

    r = await c.post("/api/pay/invoice", json={"plan": "1oy"})
    assert r.status_code == 409 and "chek" in r.json()["detail"]

    _enable(monkeypatch)
    app.state.bot = FakeBot()
    assert (await c.get("/api/pay/info")).json()["auto_pay"] is True
    assert (await c.post("/api/pay/invoice", json={"plan": "yoq"})).status_code == 422
    r = await c.post("/api/pay/invoice", json={"plan": "3oy"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["url"].startswith("https://t.me/$") and d["amount"] == 100_000 and d["provider"] == "Payme"

    class BrokenBot(FakeBot):
        async def create_invoice_link(self, **kw):
            raise RuntimeError("PAYMENT_PROVIDER_INVALID")

    app.state.bot = BrokenBot()
    assert (await c.post("/api/pay/invoice", json={"plan": "1oy"})).status_code == 503


class FakeSession:
    def __init__(self):
        self.calls = []

    async def __call__(self, bot, method, timeout=None):
        self.calls.append(method)
        return None

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_bot_router(session_factory, monkeypatch):
    from aiogram import Bot, Dispatcher
    from aiogram.types import Chat, Message, PreCheckoutQuery, Update, User as TgUser

    from bot import payments as mod
    from config import settings

    monkeypatch.setattr(mod, "SessionLocal", session_factory)
    monkeypatch.setattr(settings, "admin_id", 999)
    async with session_factory() as s:
        u = User(tg_id=4242, name="Nodir")
        s.add(u)
        await s.commit()
        uid = u.id

    bot = Bot(token="42:TESTTOKEN")
    bot.session = FakeSession()
    dp = Dispatcher()
    dp.include_router(mod.router)
    tg_user = TgUser(id=4242, is_bot=False, first_name="N")
    try:
        q = PreCheckoutQuery(id="q1", from_user=tg_user, currency="UZS", total_amount=4_000_000,
                             invoice_payload=f"vip:1oy:{uid}:40000")
        await dp.feed_update(bot, Update(update_id=1, pre_checkout_query=q))
        m = bot.session.calls[-1]
        assert type(m).__name__ == "AnswerPreCheckoutQuery" and m.ok is True and m.pre_checkout_query_id == "q1"

        bad = PreCheckoutQuery(id="q2", from_user=tg_user, currency="UZS", total_amount=100,
                               invoice_payload=f"vip:1oy:{uid}:40000")
        await dp.feed_update(bot, Update(update_id=2, pre_checkout_query=bad))
        m = bot.session.calls[-1]
        assert m.ok is False and "Summa" in m.error_message

        msg = Message(
            message_id=3, date=datetime.now(), chat=Chat(id=4242, type="private"), from_user=tg_user,
            successful_payment=_sp(f"vip:1oy:{uid}:40000", 4_000_000, charge="tg-ch-1"),
        )
        bot.session.calls.clear()
        await dp.feed_update(bot, Update(update_id=3, message=msg))
        sends = [c for c in bot.session.calls if type(c).__name__ == "SendMessage"]
        assert [x.chat_id for x in sends] == [4242, 999] and "VIP yoqildi" in sends[0].text
        async with session_factory() as s:
            row = (await s.execute(select(PaymentRequest))).scalar_one()
            assert row.provider == "telegram" and row.charge_id == "tg-ch-1" and row.status == "approved"
            assert billing.is_vip((await s.execute(select(User).where(User.id == uid))).scalar_one())
    finally:
        mod.router._parent_router = None
