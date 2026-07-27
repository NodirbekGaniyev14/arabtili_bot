"""Oylik reyting sovrini (top-5) va davr yakuni idempotentligi."""

from datetime import timedelta

import pytest

from db.models import Meta, User, WeeklyAward, XpLog
from services.league import _month_start_utc, top_winners
import services.weekly as wk


class FakeBot:
    def __init__(self):
        self.photos = []

    async def send_photo(self, chat, photo, caption="", **kw):
        self.photos.append((chat, caption))

    async def send_message(self, *a, **kw):
        pass


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


async def test_monthly_rollover_awards_top5(session_factory, monkeypatch):
    """O'tgan oyda 6 kishi XP yig'sa — top-5 sovrin oladi, 6-chi olmaydi."""
    import db.session as dbs

    monkeypatch.setattr(dbs, "SessionLocal", session_factory)
    monkeypatch.setattr(wk, "SessionLocal", session_factory)

    prev = wk._prev_month_start(_month_start_utc())
    async with session_factory() as s:
        for i, xp in enumerate([600, 500, 400, 300, 200, 100]):
            await _user_xp(s, f"M{i}", xp, prev + timedelta(days=2))

    bot = FakeBot()
    await wk._monthly_rollover(bot)

    assert len(bot.photos) == 5  # top-5

    async with session_factory() as s:
        awards = (await s.execute(__import__("sqlalchemy").select(WeeklyAward))).scalars().all()
        assert len(awards) == 5
        assert all(a.period == "month" for a in awards)
        assert {a.rank for a in awards} == {1, 2, 3, 4, 5}

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
