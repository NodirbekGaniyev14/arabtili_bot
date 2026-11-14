"""K34 qaytish kampaniyasi: 7–120 kun jim o'quvchiga 1 savollik viktorina; 7 kun ichida dars o'tsa streak + 50 XP."""

import json
from datetime import timedelta

import pytest

from db.models import ComebackOffer, Plan, Progress, User, UserWord, XpLog, utcnow
from services import comeback as cb
from services.stats import TASHKENT_OFFSET, _local_date

# Toshkent 12:00 — yuborish oynasi ichida
NOON = (utcnow() + TASHKENT_OFFSET).replace(hour=12, minute=0, second=0, microsecond=0) - TASHKENT_OFFSET


class FakeBot:
    def __init__(self, blocked=()):
        self.sent, self.blocked = [], set(blocked)

    async def send_message(self, chat_id, text, **kw):
        if chat_id in self.blocked:
            raise RuntimeError("Forbidden: bot was blocked by the user")
        self.sent.append((chat_id, text, kw.get("reply_markup")))


async def _learner(session, name, idle_days, *, streak=0, words=True, **kw):
    """`idle_days` kun oldin oxirgi faollik; undan oldin `streak` kun ketma-ket faol."""
    u = User(tg_id=10_000 + abs(hash(name)) % 10**6, name=name, **{"is_demo": 0, **kw})
    session.add(u)
    await session.flush()
    last = NOON - timedelta(days=idle_days)
    session.add(Plan(user_id=u.id, level="A1", target_level="A2", target_date="2027-01-01",
                     created_at=last - timedelta(days=max(streak, 1))))
    for i in range(max(streak, 1)):
        session.add(XpLog(user_id=u.id, amount=10, source="lesson:a1-01", created_at=last - timedelta(days=i)))
    if words:
        for ar, uz, reps in (("كَبِير", "katta", 3), ("صَغِير", "kichik", 2), ("جَدِيد", "yangi", 1), ("قَدِيم", "eski", 0)):
            session.add(UserWord(user_id=u.id, ar=ar, uz=uz, due_date="2026-01-01", reps=reps))
    await session.commit()
    return u


@pytest.mark.asyncio
async def test_audience_7_to_120_days_comeback_on_once(session):
    ok = await _learner(session, "Ok", 10)
    await _learner(session, "Yaqin", 3)
    await _learner(session, "Eski", 130)
    await _learner(session, "Ochiq", 60, notify_off="comeback")
    await _learner(session, "Demo", 20, is_demo=1)
    w = await _learner(session, "Winback", 30)
    w.winback_at = NOON - timedelta(hours=5)  # bugun 30 kunlik winback xabari olgan
    await session.commit()

    aud = await cb.audience(session, NOON)
    assert [u.name for u, _, _ in aud["users"]] == ["Ok"]
    assert aud["off"] == 1 and aud["recent"] == 1 and aud["buckets"][(7, 14)] == 1

    session.add(ComebackOffer(user_id=ok.id, campaign="old", sent_at=NOON - timedelta(days=30)))
    await session.commit()
    assert (await cb.audience(session, NOON))["users"] == [], f"{cb.REPEAT_DAYS} kunda bir marta"


@pytest.mark.asyncio
async def test_quiz_uses_own_practised_word_and_clean_options(session):
    u = await _learner(session, "Ali", 10)
    q = await cb.pick_quiz(session, u)
    assert q["ar"] in ("كَبِير", "صَغِير", "جَدِيد") and not q["letter"], "mashq qilingan so'z (reps > 0)"
    assert len(q["options"]) == 3 and q["answer"] in q["options"] and len(set(q["options"])) == 3

    new = await _learner(session, "Yangi", 10, words=False)
    q = await cb.pick_quiz(session, new)
    assert q["answer"] in q["options"] and len(q["options"]) == 3, "kartasi yo'q — kurs boshidan"


@pytest.mark.asyncio
async def test_send_answer_and_blocked(session):
    a = await _learner(session, "Ali", 10, streak=6)
    b = await _learner(session, "Bek", 20)
    bot = FakeBot(blocked={b.tg_id})
    res = await cb.send_campaign(session, bot, NOON)
    assert (res["sent"], res["failed"]) == (1, 1)
    chat, text, kb = bot.sent[0]
    assert chat == a.tg_id and "10 kundan beri" in text and "esingizdami" in text
    offer = (await session.execute(ComebackOffer.__table__.select().where(ComebackOffer.user_id == a.id))).one()
    assert offer.prior_streak == 6 and offer.status == "sent"
    buttons = [row[0] for row in kb.inline_keyboard]
    assert [x.text for x in buttons] == json.loads(offer.options_json)
    failed = (await session.execute(ComebackOffer.__table__.select().where(ComebackOffer.user_id == b.id))).one()
    assert failed.status == "failed", "bloklagan — qayta urinilmaydi"

    # Boshqa odam bosa olmaydi; to'g'ri javob — natija + sovg'a sharti
    right = json.loads(offer.options_json).index(offer.quiz_answer)
    assert (await cb.answer(session, offer.id, b.tg_id, right))[0] is None
    text, toast = await cb.answer(session, offer.id, a.tg_id, right)
    assert toast == "✅ To'g'ri!" and "6 kunlik streakingiz tiklanadi" in text and "+50 XP" in text
    assert "4 ta kartangiz" in text
    again, toast = await cb.answer(session, offer.id, a.tg_id, right)
    assert again is None and "Javob berilgan" in toast


@pytest.mark.asyncio
async def test_claim_restores_streak_and_gives_xp_once(session):
    a = await _learner(session, "Ali", 10, streak=6)
    lazy = await _learner(session, "Dangasa", 12)
    await cb.send_campaign(session, FakeBot(), NOON)
    bot = FakeBot()
    assert await cb.claim_due(session, bot, NOON + timedelta(hours=1)) == 0, "dars o'tilmagan"

    # Ali qaytdi: dars o'tdi (taklifdan keyin)
    back = NOON + timedelta(hours=2)
    session.add(Progress(user_id=a.id, lesson_id="a1-02", correct=5, total=6, passed=1, completed_at=back))
    session.add(XpLog(user_id=a.id, amount=20, source="lesson:a1-02", created_at=back))
    # Dangasa — faqat yiqilgan urinish
    session.add(Progress(user_id=lazy.id, lesson_id="a1-02", correct=1, total=6, passed=0, completed_at=back))
    await session.commit()

    assert await cb.claim_due(session, bot, back + timedelta(minutes=20)) == 1
    msg = bot.sent[0][1]
    assert bot.sent[0][0] == a.tg_id and "Streak tiklandi: <b>7 kun</b>" in msg and "+50 XP" in msg
    xp = (await session.execute(XpLog.__table__.select().where(XpLog.source.like("comeback:%")))).all()
    assert [r.amount for r in xp] == [cb.GIFT_XP]
    assert await cb.claim_due(session, bot, back + timedelta(hours=1)) == 0, "bir marta"

    text = await cb.results_text(session)
    assert "yetdi 2" in text and "qaytib dars o'tdi 1 (50%)" in text


@pytest.mark.asyncio
async def test_claim_window_closes(session):
    a = await _learner(session, "Ali", 10, streak=3)
    await cb.send_campaign(session, FakeBot(), NOON)
    late = NOON + timedelta(days=cb.CLAIM_DAYS + 1)
    session.add(Progress(user_id=a.id, lesson_id="a1-02", correct=5, total=6, passed=1, completed_at=late))
    await session.commit()
    assert await cb.claim_due(session, FakeBot(), late) == 0


@pytest.mark.asyncio
async def test_winback_skips_offered_users(session):
    from services import winback

    a = await _learner(session, "Ali", 10)
    await cb.send_campaign(session, FakeBot(), NOON)
    bot = FakeBot()
    out = await winback.process(session, bot, NOON + timedelta(hours=1))
    assert a.tg_id not in [c for c, _, _ in bot.sent] and out[7] == 0


def test_streak_until_and_send_hours():
    from datetime import date

    d = date(2026, 11, 10)
    active = {d, d - timedelta(days=1), d - timedelta(days=3)}
    assert cb.streak_until(active, set(), d) == 2
    assert cb.streak_until(active, {d - timedelta(days=2)}, d) == 3, "muzlatilgan kun zanjirni uzmaydi"
    assert cb.in_send_hours(NOON) and not cb.in_send_hours(NOON + timedelta(hours=10))
    assert _local_date(NOON).isoformat()


class FakeMessage:
    def __init__(self, tg_id, text):
        from types import SimpleNamespace

        self.from_user = SimpleNamespace(id=tg_id)
        self.chat = SimpleNamespace(id=tg_id)
        self.text = text
        self.answers = []

    async def answer(self, text, **kw):
        self.answers.append(text)


@pytest.mark.asyncio
async def test_admin_command_preview_results_and_night_guard(session, session_factory, monkeypatch):
    import bot.admin as adm
    from config import settings

    monkeypatch.setattr(settings, "admin_id", 999)
    monkeypatch.setattr(adm, "SessionLocal", session_factory)
    await _learner(session, "Ali", 10)
    bot = FakeBot()

    m = FakeMessage(999, "/qaytarish")
    await adm.cmd_comeback(m, bot)
    assert bot.sent and bot.sent[0][0] == 999 and "Namuna" in bot.sent[0][1], "namuna adminning o'ziga"
    assert "Yuboriladi: <b>1</b> kishi" in m.answers[0] and "/qaytarish yubor" in m.answers[0]
    assert (await session.execute(ComebackOffer.__table__.select())).all() == [], "namuna bazaga yozilmaydi"

    m = FakeMessage(999, "/qaytarish natija")
    await adm.cmd_comeback(m, bot)
    assert "hali yuborilmagan" in m.answers[0]

    monkeypatch.setattr(adm, "utcnow", lambda: NOON + timedelta(hours=11), raising=False)
    monkeypatch.setattr("db.models.utcnow", lambda: NOON + timedelta(hours=11))
    m = FakeMessage(999, "/qaytarish yubor")
    await adm.cmd_comeback(m, bot)
    assert "Faqat kunduzi" in m.answers[0]

    m = FakeMessage(1, "/qaytarish")  # admin emas
    await adm.cmd_comeback(m, bot)
    assert m.answers == []
