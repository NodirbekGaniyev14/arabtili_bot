"""K29.2 — sinov davri eslatmalari: ustozga yozmagan sinovchiga bir marta turtki, tugashiga 6 soat qolganda qiymat eslatmasi."""

from datetime import datetime, timedelta

import pytest

from config import settings
from db.models import TutorTurn
from services import referral
from services import vip_reminders as vr

NOON = datetime(2026, 9, 15, 7, 0, 0)  # 12:00 Toshkent
NIGHT = datetime(2026, 9, 15, 19, 0, 0)  # 00:00 Toshkent


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, reply_markup=None, **kw):
        self.sent.append((chat_id, text, reply_markup))


@pytest.fixture(autouse=True)
def _cfg(monkeypatch):
    monkeypatch.setattr(settings, "pay_old_price_month", 90_000)
    monkeypatch.setattr(settings, "pay_old_price_3month", 240_000)
    monkeypatch.setattr(settings, "admin_id", 0)
    monkeypatch.setattr(settings, "webapp_url", "https://arabiy.example/app")


async def _trial_user(make_user, name: str, elapsed_h: float):
    """Sinov `elapsed_h` soat oldin boshlangan (NOON ga nisbatan)."""
    u = await make_user(name)
    u.trial_until = NOON - timedelta(hours=elapsed_h) + timedelta(days=referral.TRIAL_DAYS)
    u.vip_until = u.trial_until
    return u


@pytest.mark.asyncio
async def test_start_nudge_for_silent_trial_user_once(session, make_user):
    u = await _trial_user(make_user, "Jim", 4)
    await session.commit()
    bot = FakeBot()
    r = await vr.process(session, bot, NOON)
    assert r["trial"] == 1 and len(bot.sent) == 1
    chat, text, kb = bot.sent[0]
    assert chat == u.tg_id and "sinovingiz faol" in text and "~44 soatdan" in text
    assert kb.inline_keyboard[0][0].web_app.url.endswith("#tutor"), "tugma to'g'ridan-to'g'ri ustozni ochadi"
    assert u.trial_nudge == 1
    assert (await vr.process(session, bot, NOON + timedelta(hours=1)))["trial"] == 0, "qayta yuborilmaydi"


@pytest.mark.asyncio
async def test_no_start_nudge_when_too_early_or_already_active_or_too_late(session, make_user):
    early = await _trial_user(make_user, "Erta", 2)
    active = await _trial_user(make_user, "Faol", 5)
    late = await _trial_user(make_user, "Kech", 36)
    session.add(TutorTurn(user_id=active.id, session_key="s", created_at=NOON - timedelta(hours=4)))
    await session.commit()
    bot = FakeBot()
    r = await vr.process(session, bot, NOON)
    assert r["trial"] == 0 and bot.sent == []
    assert early.trial_nudge == 0, "3 soat o'tmagan — keyinroq"
    assert active.trial_nudge == 1, "yozgan — jim belgilanadi"
    assert late.trial_nudge == 1, "30 soatdan keyin «boshlang» demaymiz — belgilanadi, xabarsiz"


@pytest.mark.asyncio
async def test_last_nudge_reports_usage_and_promises_offer_only_when_enabled(session, make_user, monkeypatch):
    u = await _trial_user(make_user, "Faol", 43)  # ~5 soat qoldi
    for i in range(3):
        session.add(TutorTurn(user_id=u.id, session_key="s", created_at=NOON - timedelta(hours=10, minutes=i)))
    u.trial_nudge = 1
    await session.commit()
    bot = FakeBot()
    r = await vr.process(session, bot, NOON)
    assert r["trial"] == 1
    text = bot.sent[0][1]
    assert "Hozircha 3 ta suhbat javobi" in text and "mock imtihon" in text
    assert "maxsus narx" in text and "so'm" not in text, "narx aytilmaydi: tugagach yangi oyna ochiladi"
    assert u.trial_nudge == 3
    assert (await vr.process(session, bot, NOON + timedelta(hours=1)))["trial"] == 0

    v = await _trial_user(make_user, "Chegirmasiz", 43)
    v.trial_nudge = 1
    await session.commit()
    monkeypatch.setattr(settings, "pay_old_price_month", 0)  # chegirma o'chiq → va'da yo'q
    bot = FakeBot()
    await vr.process(session, bot, NOON)
    mine = [t for c, t, _ in bot.sent if c == v.tg_id]
    assert len(mine) == 1 and "maxsus narx" not in mine[0] and "Hali ustoz bilan gaplashib ko'rmadingiz" in mine[0]


@pytest.mark.asyncio
async def test_no_nudges_at_night_or_for_paid_vip(session, make_user):
    u = await _trial_user(make_user, "Tun", 4)
    paid = await make_user("Tolagan", vip_until=NOON + timedelta(days=20))
    paid.trial_until = NOON - timedelta(days=60)  # sinov ilgari bo'lgan
    await session.commit()
    bot = FakeBot()
    assert (await vr.process(session, bot, NIGHT))["trial"] == 0 and bot.sent == []
    assert u.trial_nudge == 0, "tunda yuborilmaydi va belgilanmaydi — ertalab boradi"
    r = await vr.process(session, bot, NIGHT + timedelta(hours=10))
    assert r["trial"] == 1 and [c for c, _, _ in bot.sent] == [u.tg_id]
    assert paid.trial_nudge == 0
