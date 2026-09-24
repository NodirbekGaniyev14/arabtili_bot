"""K17.4 — VIP eslatmalari: muddat tugashi (3 kun / tugagan), chegirma taymeri,
admin kunlik chek ro'yxati; har biri bir marta, faqat kunduzi."""

from datetime import datetime, timedelta

import pytest

from db.models import PaymentRequest, User, utcnow
from services import vip_reminders as vr


class FakeBot:
    def __init__(self):
        self.sent: list[tuple[int, str, object]] = []

    async def send_message(self, chat_id, text, reply_markup=None, **kw):
        self.sent.append((chat_id, text, reply_markup))


# 12:00 Toshkent = 07:00 UTC (kunduz); 03:00 Toshkent = 22:00 UTC (tun)
NOON = datetime(2026, 9, 15, 7, 0, 0)
NIGHT = datetime(2026, 9, 14, 22, 0, 0)
NINE = datetime(2026, 9, 15, 4, 0, 0)  # 09:00 Toshkent


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "admin_id", 0)
    monkeypatch.setattr(settings, "webapp_url", "https://arabiy.example/app")
    monkeypatch.setattr(settings, "pay_price_month", 40_000)
    monkeypatch.setattr(settings, "pay_old_price_month", 90_000)
    monkeypatch.setattr(settings, "pay_discount_hours", 24)
    monkeypatch.setattr(vr, "_digest_sent_on", "")


@pytest.mark.asyncio
async def test_soon_once_per_period(session, make_user):
    u = await make_user("Nodir", vip_until=NOON + timedelta(days=2, hours=3))
    far = await make_user("Far", vip_until=NOON + timedelta(days=10))
    bot = FakeBot()
    assert (await vr.process(session, bot, NOON))["soon"] == 1
    assert len(bot.sent) == 1 and bot.sent[0][0] == u.tg_id
    text, kb = bot.sent[0][1], bot.sent[0][2]
    assert "3 kundan keyin" in text and "40 000 so'm" in text
    assert kb is not None and kb.inline_keyboard[0][0].web_app.url.endswith("#vip")
    assert u.vip_notice.startswith("soon:")
    assert far.vip_notice == ""
    # Takror chaqiruv — jim
    assert (await vr.process(session, bot, NOON + timedelta(hours=1)))["soon"] == 0
    # Uzaytirdi → yangi davr, 3 kun qolganda yana bir marta
    # (billing.grant haqiqiy utcnow'ga tayanadi — test sanasi o'tib ketgach tasodifiy bo'lardi;
    #  shuning uchun muddat NOON'ga nisbatan qo'lda uzaytiriladi)
    u.vip_until = u.vip_until + timedelta(days=30)
    await session.commit()
    assert (await vr.process(session, bot, NOON + timedelta(days=1)))["soon"] == 0
    later = u.vip_until - timedelta(days=1)
    assert (await vr.process(session, bot, later))["soon"] == 1
    assert "bugun" in bot.sent[-1][1] or "kundan keyin" in bot.sent[-1][1]


@pytest.mark.asyncio
async def test_expired_once_and_window(session, make_user):
    u = await make_user("Ali", vip_until=NOON - timedelta(hours=2))
    old = await make_user("Old", vip_until=NOON - timedelta(days=10))
    bot = FakeBot()
    r = await vr.process(session, bot, NOON)
    assert r["expired"] == 1 and r["soon"] == 0
    assert bot.sent[0][0] == u.tg_id and "tugadi" in bot.sent[0][1]
    assert u.vip_notice.startswith("expired:") and old.vip_notice == ""
    assert (await vr.process(session, bot, NOON + timedelta(hours=3)))["expired"] == 0


@pytest.mark.asyncio
async def test_discount_two_hours_before_end(session, make_user):
    seen = NOON - timedelta(hours=22, minutes=30)  # 1.5 soat qoldi
    u = await make_user("Zara", paywall_seen_at=seen)
    early = await make_user("Early", paywall_seen_at=NOON - timedelta(hours=10))
    # is_vip real soatga qaraydi — NOON o'tib ketgan sanalarda ham VIP qolsin
    vip = await make_user("Vip", paywall_seen_at=seen, vip_until=max(NOON, utcnow()) + timedelta(days=9))
    paid = await make_user("Paid", paywall_seen_at=seen)
    session.add(PaymentRequest(user_id=paid.id, plan="1oy", amount=40_000))
    await session.commit()

    bot = FakeBot()
    assert (await vr.process(session, bot, NOON))["discount"] == 1
    assert bot.sent[0][0] == u.tg_id
    text = bot.sent[0][1]
    assert "56% chegirmangiz 1 soat 30 daqiqadan keyin tugaydi" in text
    assert "40 000 so'm" in text and "90 000" in text
    assert u.discount_notified == 1
    assert early.discount_notified == 0 and vip.discount_notified == 0
    assert paid.discount_notified == 0
    assert (await vr.process(session, bot, NOON + timedelta(minutes=15)))["discount"] == 0


@pytest.mark.asyncio
async def test_discount_skipped_when_disabled(session, make_user, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "pay_old_price_month", 0)
    await make_user("Z", paywall_seen_at=NOON - timedelta(hours=22, minutes=30))
    bot = FakeBot()
    assert (await vr.process(session, bot, NOON))["discount"] == 0 and bot.sent == []


@pytest.mark.asyncio
async def test_quiet_hours_hold_user_messages(session, make_user):
    u = await make_user("N", vip_until=NIGHT + timedelta(days=1))
    bot = FakeBot()
    r = await vr.process(session, bot, NIGHT)
    assert r == {"soon": 0, "expired": 0, "discount": 0, "digest": 0}
    assert u.vip_notice == ""
    # Ertalab yuboriladi
    assert (await vr.process(session, bot, NIGHT + timedelta(hours=10)))["soon"] == 1


@pytest.mark.asyncio
async def test_demo_users_ignored(session, make_user):
    await make_user("Demo", vip_until=NOON + timedelta(days=1), is_demo=1)
    bot = FakeBot()
    assert (await vr.process(session, bot, NOON))["soon"] == 0 and bot.sent == []


@pytest.mark.asyncio
async def test_admin_digest_at_nine_once(session, make_user, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "admin_id", 99)
    u = await make_user("Payer", username="payer")
    session.add(
        PaymentRequest(
            user_id=u.id, plan="3oy", amount=100_000, created_at=NINE - timedelta(hours=20)
        )
    )
    await session.commit()
    bot = FakeBot()
    assert (await vr.process(session, bot, NINE - timedelta(hours=1)))["digest"] == 0
    assert (await vr.process(session, bot, NINE))["digest"] == 1
    chat, text, _ = bot.sent[-1]
    assert chat == 99 and "1 ta chek" in text and "@payer" in text and "20 soat" in text
    assert (await vr.process(session, bot, NINE + timedelta(minutes=15)))["digest"] == 0
    # Ertasi kuni yana
    assert (await vr.process(session, bot, NINE + timedelta(days=1)))["digest"] == 1


@pytest.mark.asyncio
async def test_admin_digest_silent_without_pending(session, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "admin_id", 99)
    bot = FakeBot()
    assert (await vr.process(session, bot, NINE))["digest"] == 0 and bot.sent == []


def test_keyboard_none_without_https(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "webapp_url", "")
    assert vr.paywall_keyboard("x") is None


@pytest.mark.asyncio
async def test_blocked_user_does_not_break_loop(session, make_user):
    a = await make_user("A", vip_until=NOON + timedelta(days=1))
    b = await make_user("B", vip_until=NOON + timedelta(days=1))

    class Bot(FakeBot):
        async def send_message(self, chat_id, text, **kw):
            if chat_id == a.tg_id:
                raise RuntimeError("Forbidden: bot was blocked")
            await super().send_message(chat_id, text, **kw)

    bot = Bot()
    assert (await vr.process(session, bot, NOON))["soon"] == 1
    assert bot.sent[0][0] == b.tg_id
    assert a.vip_notice and b.vip_notice, "bloklaganga ham qayta urinilmaydi"
