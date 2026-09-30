"""K29 — rad etilgan chek: sabab, sababga mos xabar, qayta yuborish yo'li; sinov tugaganda yangi narx oynasi;
kartadagi narx paywall bilan bir xil (ilgari 40 000 ↔ 90 000 nomuvofiqligi)."""

from datetime import datetime, timedelta

import pytest

from config import settings
from db.models import PaymentRequest, TutorTurn, User, utcnow
from services import billing, referral
from services import vip_reminders as vr

NOON = datetime(2026, 9, 15, 7, 0, 0)  # 12:00 Toshkent


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, reply_markup=None, **kw):
        self.sent.append((chat_id, text, reply_markup))


@pytest.fixture(autouse=True)
def _prices(monkeypatch):
    monkeypatch.setattr(settings, "pay_price_month", 40_000)
    monkeypatch.setattr(settings, "pay_price_3month", 100_000)
    monkeypatch.setattr(settings, "pay_old_price_month", 90_000)
    monkeypatch.setattr(settings, "pay_old_price_3month", 240_000)
    monkeypatch.setattr(settings, "pay_discount_hours", 24)
    monkeypatch.setattr(settings, "admin_id", 0)
    monkeypatch.setattr(settings, "webapp_url", "https://arabiy.example/app")
    monkeypatch.setattr(settings, "support_username", "arabiy_admin")


def test_admin_keyboard_offers_reasons_and_keeps_approvals():
    kb = billing.admin_keyboard(7).inline_keyboard
    data = [b.callback_data for row in kb for b in row]
    assert data == ["pay:ok:7:30", "pay:ok:7:90", "pay:no:7:low", "pay:no:7:blur", "pay:no:7:none"]


def test_rejection_texts_are_specific():
    low = billing.user_rejected_text("low", 90_000)
    assert "90 000 so'm" in low and "Farqini o'tkazing" in low and "@arabiy_admin" in low
    assert "aniq o'qilmadi" in billing.user_rejected_text("blur")
    assert "to'lov tushmadi" in billing.user_rejected_text("none")
    assert "tasdiqlanmadi" in billing.user_rejected_text() == billing.user_rejected_text("nomalum")


@pytest.mark.asyncio
async def test_reject_stores_reason_and_lists_recent(session, make_user):
    u = await make_user("Ali")
    a = PaymentRequest(user_id=u.id, plan="1oy", amount=90_000)
    b = PaymentRequest(user_id=u.id, plan="3oy", amount=240_000)
    c = PaymentRequest(user_id=u.id, plan="1oy", amount=40_000, created_at=utcnow() - timedelta(days=60))
    session.add_all([a, b, c])
    await session.commit()
    await billing.reject(session, a, "low")
    await billing.reject(session, b, "xato-kod")
    await billing.reject(session, c, "blur")
    assert (a.status, a.reject_reason) == ("rejected", "low")
    assert b.reject_reason == "", "noma'lum kod saqlanmaydi"
    await billing.reject(session, a, "none")
    assert a.reject_reason == "low", "qayta bosilsa o'zgarmaydi"
    rows = await billing.rejected_recent(session, 30)
    assert [r.id for r, _ in rows] == [b.id, a.id], "60 kunlik eski chek ro'yxatga kirmaydi, yangisi birinchi"


def test_card_price_matches_paywall(monkeypatch):
    u = User(tg_id=1, name="x")
    assert billing.price_summary(u)["month"] == 40_000, "paywall hali ochilmagan: ochganda 40 000 beriladi"
    u.paywall_seen_at = utcnow() - timedelta(hours=2)
    assert billing.price_summary(u)["month"] == billing.current_price("1oy", u) == 40_000
    u.paywall_seen_at = utcnow() - timedelta(days=2)
    assert billing.price_summary(u) == {"month": 90_000, "per_day": 3000}
    assert billing.price_summary(u)["month"] == billing.current_price("1oy", u), "karta paywall bilan bir xil"
    monkeypatch.setattr(settings, "pay_old_price_month", 0)  # chegirma o'chiq → doim bitta narx
    assert billing.price_summary(u)["month"] == billing.current_price("1oy", u) == 40_000


@pytest.mark.asyncio
async def test_trial_end_restarts_price_window_and_reports_usage(session, make_user):
    u = await make_user("Sinovchi")
    end = NOON - timedelta(hours=1)
    u.trial_until = end
    u.vip_until = end
    u.paywall_seen_at = end - timedelta(days=2)  # paywall sinov boshida ochilgan — 24 soat allaqachon tugagan
    for i in range(5):
        session.add(TutorTurn(user_id=u.id, session_key="s", created_at=end - timedelta(hours=5, minutes=i)))
    await session.commit()
    assert billing.current_price("1oy", u) == 90_000, "tuzatishdan oldin sinovdan keyin hamma 90 000 ni ko'rardi"

    bot = FakeBot()
    assert (await vr.process(session, bot, NOON))["expired"] == 1
    text = bot.sent[0][1]
    assert "Sinov davomida 5 ta suhbat javobi berdingiz" in text
    assert "Faqat 24 soat" in text and "40 000 so'm" in text and "keyin 90 000" in text
    assert u.paywall_seen_at == NOON and u.discount_notified == 0, "narx oynasi sinov tugagan paytdan qayta ochildi"
    assert billing.discount_active(u, NOON) and billing.discount_until(u) == NOON + timedelta(hours=24)
    # 22 soatdan keyin «chegirma tugayapti» eslatmasi ham ishlaydi (2-nudge)
    r = await vr.process(session, bot, NOON + timedelta(hours=22, minutes=5))
    assert r["discount"] == 1 and "chegirmangiz" in bot.sent[-1][1]


@pytest.mark.asyncio
async def test_paid_vip_expiry_does_not_restart_window(session, make_user):
    u = await make_user("Tolagan")
    u.vip_until = NOON - timedelta(hours=1)
    u.trial_until = NOON - timedelta(days=40)  # sinov ilgari bo'lgan, hozirgi VIP boshqa (uzaytirilgan)
    old_seen = NOON - timedelta(days=30)
    u.paywall_seen_at = old_seen
    await session.commit()
    bot = FakeBot()
    assert (await vr.process(session, bot, NOON))["expired"] == 1
    assert u.paywall_seen_at == old_seen and "VIP muddatingiz tugadi" in bot.sent[0][1]
    assert "90 000 so'm" in bot.sent[0][1], "to'lagan mijozga ham haqiqiy narx aytiladi"


class _FakeSession:
    def __init__(self):
        self.calls = []

    async def __call__(self, bot, method, timeout=None):
        self.calls.append(method)
        return None

    async def close(self):
        pass


async def _press(session_factory, monkeypatch, data: str):
    """Admin chek ostidagi tugmani bosadi (haqiqiy aiogram marshruti). Qaytaradi: (req_id, yuborilgan xabarlar)."""
    from aiogram import Bot, Dispatcher
    from aiogram.types import CallbackQuery, Chat, Message, Update, User as TgUser

    from bot import admin as mod
    from bot.admin import router as admin_router

    admin_id = 777001
    monkeypatch.setattr(mod, "SessionLocal", session_factory)
    monkeypatch.setattr(settings, "admin_id", admin_id)
    async with session_factory() as s:
        u = User(tg_id=555, name="Xaridor")
        s.add(u)
        await s.flush()
        req = PaymentRequest(user_id=u.id, plan="1oy", amount=90_000)
        s.add(req)
        await s.commit()
        req_id = req.id
    bot = Bot(token="42:TESTTOKEN")
    bot.session = _FakeSession()
    dp = Dispatcher()
    dp.include_router(admin_router)
    chat = Chat(id=admin_id, type="private")
    admin = TgUser(id=admin_id, is_bot=False, first_name="A")
    msg = Message(message_id=5, date=datetime.now(), chat=chat, from_user=admin, text="chek")
    try:
        for i in (1, 2):  # ikki marta bosilsa ham foydalanuvchiga bitta xabar
            cb = CallbackQuery(id=str(i), from_user=admin, chat_instance="c", data=data.format(id=req_id), message=msg)
            await dp.feed_update(bot, Update(update_id=i, callback_query=cb))
    finally:
        admin_router._parent_router = None
    sent = [c for c in bot.session.calls if type(c).__name__ == "SendMessage" and c.chat_id == 555]
    return req_id, sent


@pytest.mark.asyncio
async def test_admin_reject_low_sends_amount_and_resubmit_button(session_factory, monkeypatch):
    req_id, sent = await _press(session_factory, monkeypatch, "pay:no:{id}:low")
    assert len(sent) == 1
    assert "90 000 so'm" in sent[0].text and "Farqini o'tkazing" in sent[0].text
    assert sent[0].reply_markup.inline_keyboard[0][0].web_app.url.endswith("#vip"), "qayta yuborish tugmasi"
    async with session_factory() as s:
        req = await s.get(PaymentRequest, req_id)
        assert (req.status, req.reject_reason) == ("rejected", "low")


@pytest.mark.asyncio
async def test_admin_reject_legacy_button_still_works(session_factory, monkeypatch):
    """Eski xabarlardagi «pay:no:<id>» (sababsiz) tugmasi ham ishlaydi — umumiy matn, tugmasiz."""
    req_id, sent = await _press(session_factory, monkeypatch, "pay:no:{id}")
    assert len(sent) == 1 and "tasdiqlanmadi" in sent[0].text and sent[0].reply_markup is None
    async with session_factory() as s:
        assert (await s.get(PaymentRequest, req_id)).reject_reason == ""
