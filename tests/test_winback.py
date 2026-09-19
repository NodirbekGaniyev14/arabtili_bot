"""K20.1 — qaytarish ketma-ketligi: bosqich hisobi, nomzodlar, 3/7/30 kun xabarlari
bir marta, qaytgan foydalanuvchida bosqich nolga, 90+ kun jim — yozilmaydi."""

from datetime import datetime, timedelta

import pytest

from db.models import Plan, XpLog
from services import winback as wb


class FakeBot:
    def __init__(self):
        self.sent: list[tuple[int, str, object]] = []

    async def send_message(self, chat_id, text, reply_markup=None, **kw):
        self.sent.append((chat_id, text, reply_markup))


NOON = datetime(2026, 9, 19, 7, 0)  # 12:00 Toshkent


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "admin_id", 0)
    monkeypatch.setattr(settings, "webapp_url", "https://arabiy.example/app")
    monkeypatch.setattr(wb, "SEND_PAUSE", 0)


def test_stage_for():
    assert wb.stage_for(2, 0) == 0
    assert wb.stage_for(3, 0) == 3 and wb.stage_for(6, 0) == 3 and wb.stage_for(6, 3) == 0
    assert wb.stage_for(7, 3) == 7 and wb.stage_for(20, 0) == 7, "3 kunlik o'tkazib yuborilsa — 7"
    assert wb.stage_for(29, 7) == 0 and wb.stage_for(30, 7) == 30 and wb.stage_for(45, 0) == 30
    assert wb.stage_for(30, 30) == 0 and wb.stage_for(91, 0) == 0, "90+ kun — jim"


async def _user(session, make_user, name, days_ago, xp=True, **kw):
    u = await make_user(name, **kw)
    session.add(Plan(user_id=u.id, level="A1", target_level="A2", target_date="2027-01-01",
                     created_at=NOON - timedelta(days=days_ago + 5)))
    if xp:
        session.add(XpLog(user_id=u.id, amount=10, source="lesson:a0-01", created_at=NOON - timedelta(days=days_ago)))
    return u


@pytest.mark.asyncio
async def test_process_stages_once(session, make_user, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "admin_id", 999)
    d4 = await _user(session, make_user, "Nodir", 4)
    d10 = await _user(session, make_user, "Far", 10)
    d40 = await _user(session, make_user, "Old", 40)
    d100 = await _user(session, make_user, "Dead", 100)
    fresh = await _user(session, make_user, "Fresh", 1)
    noxp = await _user(session, make_user, "NoXp", 8, xp=False)  # reja 13 kun oldin, XP yo'q
    demo = await _user(session, make_user, "Demo", 10, is_demo=1)
    await session.commit()

    bot = FakeBot()
    assert await wb.process(session, bot, datetime(2026, 9, 19, 2, 0)) == {3: 0, 7: 0, 30: 0, "failed": 0}, "07:00 — erta"
    out = await wb.process(session, bot, NOON)
    assert out == {3: 1, 7: 2, 30: 1, "failed": 0}
    by = {c: (t, kb) for c, t, kb in bot.sent}
    assert set(by) == {d4.tg_id, d10.tg_id, d40.tg_id, noxp.tg_id, 999}
    t, kb = by[d4.tg_id]
    assert "4 kundan beri" in t and "Nodir" in t and kb.inline_keyboard[1][0].web_app.url.endswith("#daily")
    t, kb = by[d10.tg_id]
    assert "Yozuv mashqi" in t and kb.inline_keyboard[0][0].web_app.url.endswith("#writing")
    t, kb = by[d40.tg_id]
    assert "bir oy" in t and "VIP sinov" in t and kb.inline_keyboard[-1][0].web_app.url.endswith("#vip")
    assert "3 kun — 1, 7 kun — 2, 30 kun — 1" in by[999][0]
    assert d4.winback_stage == 3 and d10.winback_stage == 7 and d40.winback_stage == 30 and noxp.winback_stage == 7
    assert d100.winback_stage == 0 and fresh.winback_stage == 0 and demo.winback_stage == 0

    # Ertasi — takror yo'q; 4 kunlik foydalanuvchi 7-kunga yetganda — keyingi bosqich
    bot.sent.clear()
    assert await wb.process(session, bot, NOON + timedelta(days=1)) == {3: 0, 7: 0, 30: 0, "failed": 0}
    out = await wb.process(session, bot, NOON + timedelta(days=3))
    assert out[7] == 1 and d4.winback_stage == 7 and bot.sent[0][0] == d4.tg_id

    # Qaytib faol bo'ldi → bosqich nolga; yana 3 kun jim bo'lsa — 3-kun xabari qaytadan
    session.add(XpLog(user_id=d4.id, amount=5, source="review", created_at=NOON + timedelta(days=4)))
    await session.commit()
    bot.sent.clear()
    assert (await wb.process(session, bot, NOON + timedelta(days=5)))[3] == 0
    out = await wb.process(session, bot, NOON + timedelta(days=7, hours=1))
    assert out[3] == 1 and d4.winback_stage == 3 and "3 kundan beri" in bot.sent[0][1]


@pytest.mark.asyncio
async def test_send_failure_marks(session, make_user):
    a = await _user(session, make_user, "A", 5)
    b = await _user(session, make_user, "B", 5)
    await session.commit()

    class Bot(FakeBot):
        async def send_message(self, chat_id, text, reply_markup=None, **kw):
            if chat_id == a.tg_id:
                raise RuntimeError("blocked")
            await super().send_message(chat_id, text, reply_markup)

    bot = Bot()
    assert await wb.process(session, bot, NOON) == {3: 1, 7: 0, 30: 0, "failed": 1}
    assert a.winback_stage == 3 and [c for c, _, _ in bot.sent] == [b.tg_id]


def test_message_without_trial():
    from db.models import User

    u = User(tg_id=1, name="", trial_until=NOON)
    text, rows = wb.message(30, u, {"words": 12, "lessons": 3, "due_count": 0, "next_lesson": None}, 31)
    assert "do'stim" in text and "12 so'z" in text and "keyingi dars" in text and "VIP sinov" not in text
    assert rows == [("📚 Davom etish", "")]


@pytest.mark.asyncio
async def test_daily_reminder_skips_idle(session, make_user):
    """20:00 eslatmasi faqat oxirgi 7 kunda faollarga — jim yurganlar winback'da."""
    from services import reminders

    now = datetime.utcnow()
    a = await make_user("Active")
    session.add(XpLog(user_id=a.id, amount=5, source="lesson:x", created_at=now - timedelta(days=2)))
    b = await make_user("Idle")
    session.add(XpLog(user_id=b.id, amount=5, source="lesson:x", created_at=now - timedelta(days=12)))
    c = await make_user("NewPlan")
    session.add(Plan(user_id=c.id, level="A0", target_level="A1", target_date="2027-01-01", created_at=now - timedelta(days=1)))
    await session.flush()
    ids = await reminders.recently_active(session)
    assert a.id in ids and c.id in ids and b.id not in ids
