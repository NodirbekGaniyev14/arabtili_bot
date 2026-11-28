"""Oylik reyting sovrini (top-3) va davr yakuni idempotentligi."""

from datetime import timedelta

import pytest

from db.models import Meta, User, WeeklyAward, XpLog
from services.league import _month_start_utc, top_winners
import services.weekly as wk


class FakeBot:
    async def send_photo(self, chat, photo, caption="", **kw):
        self.photos.append((chat, caption))

    def __init__(self):
        self.photos = []
        self.messages = []

    async def send_message(self, chat, text="", **kw):
        self.messages.append((chat, text, kw.get("reply_markup")))


async def _user_xp(session, name, xp, when):
    u = User(tg_id=abs(hash(name)) % 9_000_000, name=name, is_demo=0)
    session.add(u)
    await session.flush()
    session.add(XpLog(user_id=u.id, amount=xp, source="t", created_at=when))
    await session.commit()
    return u


# ── top_winners (umumiy) ──


async def test_top_winners_respects_top_n(session):
    ws = _month_start_utc()
    for i, xp in enumerate([500, 400, 300, 200, 100, 50]):
        await _user_xp(session, f"U{i}", xp, ws + timedelta(hours=1))

    top5 = await top_winners(session, ws, top_n=5, min_participants=5)
    assert [rank for *_, rank in top5] == [1, 2, 3, 4, 5]
    assert top5[0][1] == "U0"  # eng ko'p XP


async def test_top_winners_min_participants(session):
    ws = _month_start_utc()
    for i in range(4):  # 5 tadan kam
        await _user_xp(session, f"U{i}", 100 * (i + 1), ws + timedelta(hours=1))
    assert await top_winners(session, ws, 5, 5) == []


async def test_top_winners_excludes_zero_xp(session):
    ws = _month_start_utc()
    for i, xp in enumerate([300, 200, 100, 0, 0]):
        await _user_xp(session, f"U{i}", xp, ws + timedelta(hours=1))
    # faqat 3 tasi xp>0 → 5 minimumdan kam
    assert await top_winners(session, ws, 5, 5) == []


# ── Oy yordamchilari ──


def test_month_key_and_label_shape():
    ms = _month_start_utc()
    key = wk._month_key(ms)
    assert len(key) == 7 and key[4] == "-"  # "YYYY-MM"
    label = wk._month_label(ms)
    assert any(mon in label for mon in wk.UZ_MONTHS)


def test_prev_month_is_earlier():
    ms = _month_start_utc()
    prev = wk._prev_month_start(ms)
    assert prev < ms
    # o'tgan oy kaliti joriydan farq qiladi
    assert wk._month_key(prev) != wk._month_key(ms)


def test_month_key_never_collides_with_week_key():
    """Oy kaliti 'YYYY-MM' (7), hafta kaliti 'YYYY-MM-DD' (10) — hech qachon teng emas."""
    from services.league import _week_start_utc

    wk_key = (_week_start_utc() + wk.TASHKENT_OFFSET).strftime("%Y-%m-%d")
    mo_key = wk._month_key(_month_start_utc())
    assert wk_key != mo_key
    assert len(wk_key) != len(mo_key)


# ── Oylik rollover ──


async def test_monthly_rollover_awards_top3(session_factory, monkeypatch):
    """O'tgan oyda 6 kishi XP yig'sa — top-3 sovrin oladi (👑 chempion belgisi, VIP emas), 4-chi olmaydi."""
    import db.session as dbs

    monkeypatch.setattr(dbs, "SessionLocal", session_factory)
    monkeypatch.setattr(wk, "SessionLocal", session_factory)

    prev = wk._prev_month_start(_month_start_utc())
    async with session_factory() as s:
        for i, xp in enumerate([600, 500, 400, 300, 200, 100]):
            await _user_xp(s, f"M{i}", xp, prev + timedelta(days=2))

    bot = FakeBot()
    await wk._monthly_rollover(bot)

    assert len(bot.photos) == 3  # top-3
    assert "👑 «Chempion» belgisi" in bot.photos[0][1] and "keyingi oy" in bot.photos[2][1]
    assert not any("VIP" in cap for _, cap in bot.photos), "2026-11-28: reytingda VIP yo'q"

    async with session_factory() as s:
        awards = (await s.execute(__import__("sqlalchemy").select(WeeklyAward))).scalars().all()
        assert len(awards) == 3
        assert all(a.period == "month" for a in awards)
        assert {a.rank: a.vip_days for a in awards} == {1: 0, 2: 0, 3: 0}

    # Ikkinchi marta — takror sovrin yo'q
    bot2 = FakeBot()
    await wk._monthly_rollover(bot2)
    assert bot2.photos == []


async def test_monthly_and_weekly_keys_coexist(session_factory, monkeypatch):
    """Bir foydalanuvchi ham haftalik, ham oylik sovrin olishi mumkin."""
    import db.session as dbs

    monkeypatch.setattr(dbs, "SessionLocal", session_factory)
    monkeypatch.setattr(wk, "SessionLocal", session_factory)

    from services.league import _week_start_utc

    prev_week = _week_start_utc() - timedelta(days=7)
    prev_month = wk._prev_month_start(_month_start_utc())

    async with session_factory() as s:
        for i, xp in enumerate([600, 500, 400, 300, 200]):
            u = User(tg_id=700 + i, name=f"P{i}", is_demo=0)
            s.add(u)
            await s.flush()
            # ham o'tgan haftaga, ham o'tgan oyga XP
            s.add(XpLog(user_id=u.id, amount=xp, source="t", created_at=prev_week + timedelta(hours=1)))
            s.add(XpLog(user_id=u.id, amount=xp, source="t", created_at=prev_month + timedelta(days=2)))
        await s.commit()

    await wk._rollover(FakeBot())
    await wk._monthly_rollover(FakeBot())

    async with session_factory() as s:
        awards = (await s.execute(__import__("sqlalchemy").select(WeeklyAward))).scalars().all()
        periods = {}
        for a in awards:
            periods.setdefault(a.user_id, set()).add(a.period)
        # eng yaxshi foydalanuvchi ikkala sovrinni ham olgan
        assert any(p == {"week", "month"} for p in periods.values())


# ── Sovrin: «Chempion» belgisi + muzlatkich (2026-11-28: VIP berilmaydi) ──


async def test_weekly_rollover_gives_champion_badge_not_vip(session_factory, monkeypatch):
    """Haftalik top-3: 🥇🥈🥉 «Chempion» belgisi + 1 muzlatkich (≤2); VIP yo'q; 4-o'rin — hech narsa."""
    import db.session as dbs
    from sqlalchemy import select

    from db.models import User
    from services import billing
    from services.league import _week_start_utc

    monkeypatch.setattr(dbs, "SessionLocal", session_factory)
    monkeypatch.setattr(wk, "SessionLocal", session_factory)
    prev = _week_start_utc() - timedelta(days=7)
    async with session_factory() as s:
        for i, xp in enumerate([400, 300, 200, 100]):
            await _user_xp(s, f"W{i}", xp, prev + timedelta(days=1))
        # 2-o'rin allaqachon VIP (5 kun) — o'zgarmaydi; muzlatkichi to'la (2)
        u1 = (await s.execute(select(User).where(User.name == "W1"))).scalar_one()
        billing.grant(u1, 5)
        u1.streak_freezes = 2
        u2 = (await s.execute(select(User).where(User.name == "W2"))).scalar_one()
        u2.streak_freezes = 0  # muzlatkichi tugagan — sovrin +1
        await s.commit()

    bot = FakeBot()
    await wk._rollover(bot)
    assert len(bot.photos) == 3
    caps = {c: cap for c, cap in bot.photos}
    async with session_factory() as s:
        users = {u.name: u for u in (await s.execute(select(User))).scalars().all()}
        awards = {a.rank: a for a in (await s.execute(select(WeeklyAward))).scalars().all()}
    assert not billing.is_vip(users["W0"]) and awards[1].vip_days == 0
    assert billing.vip_days_left(users["W1"]) == 5 and awards[2].vip_days == 0, "bor VIP o'zgarmaydi"
    assert not billing.is_vip(users["W2"]) and not billing.is_vip(users["W3"])
    assert users["W0"].streak_freezes == 2 and users["W1"].streak_freezes == 2, "≤ MAX_FREEZES"
    assert users["W2"].streak_freezes == 1
    assert "🥇 «Chempion» belgisi" in caps[users["W0"].tg_id] and "🥉 «Chempion» belgisi" in caps[users["W2"].tg_id]
    assert not any("VIP" in cap for cap in caps.values())
    assert [wk.badge("week", r) for r in (1, 2, 3, 4)] == ["🥇", "🥈", "🥉", ""]
    assert [wk.badge("month", r) for r in (1, 3, 4)] == ["👑", "👑", ""]
    assert wk.MONTHLY_TOP == 3 and wk.WEEKLY_TOP == 3


async def test_leaderboard_marks_vip(session, make_user):
    from services import billing
    from services.league import leaderboard

    from db.models import XpLog

    a = await make_user("Vip")
    billing.grant(a, 10)
    b = await make_user("Plain")
    for u, xp in ((a, 50), (b, 40)):
        session.add(XpLog(user_id=u.id, amount=xp, source="lesson:x"))
    await session.flush()
    data = await leaderboard(session, b.id, "week")
    by = {e["name"]: e for e in data["entries"]}
    assert by["Vip"]["vip"] is True and by["Plain"]["vip"] is False


async def test_weekly_rollover_announces_to_everyone(session_factory, monkeypatch):
    """Yakundan keyin hammaga (rejasi bor, faol) e'lon: g'oliblar, sovrin, o'z o'rni; bir marta."""
    import db.session as dbs
    from sqlalchemy import select

    from config import settings
    from db.models import Plan, User
    from services.league import _week_start_utc

    monkeypatch.setattr(dbs, "SessionLocal", session_factory)
    monkeypatch.setattr(wk, "SessionLocal", session_factory)
    monkeypatch.setattr(wk, "ANNOUNCE_PAUSE", 0)
    monkeypatch.setattr(settings, "webapp_url", "https://arabiy.example/app")
    prev = _week_start_utc() - timedelta(days=7)
    async with session_factory() as s:
        for i, xp in enumerate([400, 300, 200, 100]):
            u = await _user_xp(s, f"W{i}", xp, prev + timedelta(days=1))
            s.add(Plan(user_id=u.id, level="A1", target_level="A2", target_date="2027-01-01"))
        noplan = await _user_xp(s, "NoPlan", 50, prev + timedelta(days=1))
        old = await _user_xp(s, "Old", 5, prev - timedelta(days=100))  # 100 kun jim
        s.add(Plan(user_id=old.id, level="A1", target_level="A2", target_date="2027-01-01"))
        await s.commit()

    bot = FakeBot()
    await wk._rollover(bot)
    async with session_factory() as s:
        users = {u.name: u for u in (await s.execute(select(User))).scalars().all()}
    by = {c: (t, kb) for c, t, kb in bot.messages}
    assert set(by) == {users[n].tg_id for n in ("W0", "W1", "W2", "W3")}
    t, kb = by[users["W0"].tg_id]
    lrm = chr(0x200E)  # K27.5: ism oxirida LRM (arabcha ism yonidagi raqam joyida qolsin)
    assert "Haftalik reyting yakunlandi" in t and f"🥇 <b>W0{lrm}</b> — 400 XP\n" in t and "VIP" not in t and f"🥉 <b>W2{lrm}</b>" in t
    assert "Siz 1-o'rindasiz" in t and kb.inline_keyboard[0][0].web_app.url.endswith("#rating")
    assert "Siz: <b>4-o'rin</b>, 100 XP (5 ishtirokchi)" in by[users["W3"].tg_id][0]
    assert noplan.tg_id not in by and users["Old"].tg_id not in by

    # Takror rollover — e'lon ham takrorlanmaydi
    bot2 = FakeBot()
    await wk._rollover(bot2)
    assert bot2.messages == [] and bot2.photos == []


def test_announcement_text_no_participation():
    t = wk.announcement_text("month", "avgust 2026", [(1, "Ali", 900, 1)], None, 12)
    assert "Oylik reyting yakunlandi" in t and "Chempion» belgisi" in t and "siz hali yo'q edingiz" in t and "top-3" in t



async def test_champion_badge_shown_next_week(session, make_user):
    """O'tgan hafta top-3 va o'tgan oy top-3 — reytingda belgi; eski haftaniki ko'rinmaydi."""
    from datetime import timedelta as td

    from db.models import XpLog
    from services.league import leaderboard

    week_key, month_key = wk.champion_keys()
    a, b, c = await make_user("Birinchi"), await make_user("Oy"), await make_user("Eski")
    for u in (a, b, c):
        session.add(XpLog(user_id=u.id, amount=10, source="lesson:x"))
    session.add(WeeklyAward(user_id=a.id, week_start=week_key, period="week", rank=1, weekly_xp=400, cert_id="W1-a"))
    session.add(WeeklyAward(user_id=a.id, week_start=month_key, period="month", rank=2, weekly_xp=900, cert_id="M2-a"))
    session.add(WeeklyAward(user_id=b.id, week_start=month_key, period="month", rank=1, weekly_xp=990, cert_id="M1-b"))
    old = (__import__("datetime").date.fromisoformat(week_key) - td(days=7)).isoformat()
    session.add(WeeklyAward(user_id=c.id, week_start=old, period="week", rank=1, weekly_xp=500, cert_id="W1-c"))
    await session.flush()
    data = await leaderboard(session, c.id, "week")
    by = {e["name"]: e["champ"] for e in data["entries"]}
    assert by["Birinchi"] == "🥇👑" and by["Oy"] == "👑" and by.get("Eski", "") == ""
