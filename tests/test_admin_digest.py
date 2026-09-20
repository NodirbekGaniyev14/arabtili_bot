"""K20.3 — admin haftalik digest: o'tgan hafta raqamlari (▲/▼), sifat izohlari, g'oliblar,
dushanba bir marta (Meta marker), /digest buyrug'i."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from db.models import Meta, PaymentRequest, TutorRating, TutorTurn, User, WeeklyAward, XpLog
from services import admin_digest as ad
from services.speaking_report import week_start_utc

MONDAY = datetime(2026, 9, 21, 5, 0)  # 10:00 Toshkent


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, **kw):
        self.sent.append((chat_id, text))


@pytest.mark.asyncio
async def test_build_numbers(session, make_user):
    this_m = week_start_utc(MONDAY)
    prev = this_m - timedelta(days=7)
    prev2 = prev - timedelta(days=7)
    a = await make_user("Ali", created_at=prev + timedelta(days=1))
    b = await make_user("Bek", created_at=prev2 + timedelta(days=1), winback_at=prev + timedelta(days=2))
    session.add(XpLog(user_id=a.id, amount=10, source="lesson:a0-01", created_at=prev + timedelta(days=1)))
    session.add(XpLog(user_id=a.id, amount=10, source="lesson:a0-02", created_at=prev + timedelta(days=2)))
    session.add(XpLog(user_id=b.id, amount=5, source="review", created_at=prev + timedelta(days=3)))
    session.add(XpLog(user_id=b.id, amount=7, source="lesson:x", created_at=prev2 + timedelta(days=3)))
    session.add(TutorTurn(user_id=a.id, session_key="s", mode="chat", voice=1, created_at=prev + timedelta(days=1)))
    session.add(TutorTurn(user_id=a.id, session_key="s", mode="chat", voice=0, created_at=prev + timedelta(days=1)))
    session.add(TutorRating(user_id=a.id, session_key="s", mode="chat", topic="oila", good=0, comment="sekin", created_at=prev + timedelta(days=1)))
    session.add(TutorRating(user_id=b.id, session_key="t", mode="mock", good=1, created_at=prev + timedelta(days=1)))
    session.add(PaymentRequest(user_id=a.id, plan="1oy", amount=40_000, status="approved", days=30,
                               created_at=prev + timedelta(days=1), decided_at=prev + timedelta(days=1)))
    session.add(WeeklyAward(user_id=a.id, week_start=prev.date().isoformat() if False else (prev + timedelta(hours=5)).strftime("%Y-%m-%d"),
                            period="week", rank=1, weekly_xp=20, cert_id="W1-x"))
    await session.flush()

    cur = await ad.week_numbers(session, prev, this_m)
    assert cur["new_users"] == 1 and cur["active"] == 2 and cur["returned"] == 1
    assert cur["lessons"] == 2 and cur["xp"] == 25 and cur["chat"] == 2 and cur["voice"] == 1
    assert cur["pay_n"] == 1 and cur["pay_sum"] == 40_000 and cur["rating_n"] == 2 and cur["rating_good"] == 1
    text = await ad.build(session, MONDAY)
    assert "Haftalik digest" in text and "Yangi: <b>1</b>" in text and "Faol: <b>2</b> ▲1" in text
    assert "Qaytgan (winback): 1" in text and "🎤 50%" in text and "👍 50% (2 baho)" in text and "👎 chat · oila: sekin" in text
    assert "1 ta · 40 000 so'm ▲1" in text and "🥇 Ali (20)" in text


@pytest.mark.asyncio
async def test_maybe_send_once(session_factory, monkeypatch):
    import db.session as dbs
    from config import settings

    monkeypatch.setattr(dbs, "SessionLocal", session_factory)
    monkeypatch.setattr(settings, "admin_id", 999)
    bot = FakeBot()
    assert await ad.maybe_send(bot, datetime(2026, 9, 22, 5, 0)) is False, "seshanba"
    assert await ad.maybe_send(bot, datetime(2026, 9, 21, 2, 0)) is False, "07:00 — erta"
    assert await ad.maybe_send(bot, MONDAY) is True
    assert bot.sent[0][0] == 999 and "Haftalik digest" in bot.sent[0][1]
    assert await ad.maybe_send(bot, MONDAY + timedelta(hours=3)) is False, "bir marta"
    async with session_factory() as s:
        m = (await s.execute(select(Meta).where(Meta.key == ad.MARKER))).scalar_one()
        assert m.value == "2026-09-21"
    assert await ad.maybe_send(bot, MONDAY + timedelta(days=7)) is True and len(bot.sent) == 2
