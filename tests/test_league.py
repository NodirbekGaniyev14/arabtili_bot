"""Haftalik reyting: sana chegarasi, top-3, o'rin kuzatuvi.

Eng muhimi — `test_xp_at_week_boundary_counts`: sana MATN sifatida
solishtirilganda SQLite "2026-07-19 20:00:00" ni "2026-07-19T19:00:00"
dan kichik deb hisoblaydi (probel < "T") va hafta boshidagi XP yo'qoladi.
"""

from datetime import timedelta

from db.models import User, XpLog
from services.league import (
    _ranked_rows,
    _week_start_utc,
    league_for,
    refresh_ranks,
    weekly_top3,
)


async def _user_with_xp(session, name, amount, when, is_demo=0):
    u = User(tg_id=abs(hash(name)) % 1_000_000, name=name, is_demo=is_demo)
    session.add(u)
    await session.flush()
    session.add(XpLog(user_id=u.id, amount=amount, source="test", created_at=when))
    await session.commit()
    return u


# ── Liga darajalari ──


def test_league_thresholds():
    assert league_for(0)["id"] == "bronze"
    assert league_for(99)["id"] == "bronze"
    assert league_for(100)["id"] == "silver"
    assert league_for(299)["id"] == "silver"
    assert league_for(300)["id"] == "gold"
    assert league_for(600)["id"] == "emerald"
    assert league_for(999_999)["id"] == "emerald"


# ── Sana chegarasi (regressiya testi) ──


async def test_xp_at_week_boundary_counts(session):
    """Hafta boshi kunidagi XP reytingga kirishi SHART.

    Bu test sana solishtiruvi ISO matnga qaytarilsa yiqiladi.
    """
    ws = _week_start_utc()
    await _user_with_xp(session, "Chegara", 50, ws + timedelta(minutes=30))

    rows = await _ranked_rows(session, ws)
    assert [r.name for r in rows] == ["Chegara"]
    assert rows[0].xp == 50


async def test_xp_before_week_start_excluded(session):
    ws = _week_start_utc()
    await _user_with_xp(session, "Eski", 500, ws - timedelta(minutes=1))
    rows = await _ranked_rows(session, ws)
    assert rows == []


async def test_ranked_rows_sorted_desc(session):
    ws = _week_start_utc()
    await _user_with_xp(session, "Past", 10, ws + timedelta(hours=1))
    await _user_with_xp(session, "Yuqori", 900, ws + timedelta(hours=1))
    rows = await _ranked_rows(session, ws)
    assert [r.name for r in rows] == ["Yuqori", "Past"]


# ── Haftalik top-3 ──


async def test_top3_needs_minimum_participants(session):
    """2 kishi bilan g'olib e'lon qilinmaydi."""
    ws = _week_start_utc()
    await _user_with_xp(session, "Bir", 100, ws + timedelta(hours=1))
    await _user_with_xp(session, "Ikki", 90, ws + timedelta(hours=1))
    assert await weekly_top3(session, ws) == []


async def test_top3_returns_three_in_order(session):
    ws = _week_start_utc()
    for name, xp in [("A", 300), ("B", 200), ("C", 100), ("D", 50)]:
        await _user_with_xp(session, name, xp, ws + timedelta(hours=1))

    top = await weekly_top3(session, ws)
    assert [(name, rank) for _, name, _, rank in top] == [("A", 1), ("B", 2), ("C", 3)]


async def test_demo_users_never_win(session):
    """Demo raqiblar sovrin olmaydi va ishtirokchi sifatida sanalmaydi."""
    ws = _week_start_utc()
    for name, xp in [("Demo1", 900), ("Demo2", 800), ("Demo3", 700)]:
        await _user_with_xp(session, name, xp, ws + timedelta(hours=1), is_demo=1)
    await _user_with_xp(session, "Haqiqiy", 10, ws + timedelta(hours=1))

    assert await weekly_top3(session, ws) == []  # 1 haqiqiy < 3 minimum


async def test_zero_xp_user_not_a_winner(session):
    ws = _week_start_utc()
    for name, xp in [("A", 300), ("B", 200), ("C", 0)]:
        await _user_with_xp(session, name, xp, ws + timedelta(hours=1))
    assert await weekly_top3(session, ws) == []  # faqat 2 tasi xp>0


# ── O'rin kuzatuvi ──


async def test_first_refresh_sets_baseline_without_drops(session):
    ws = _week_start_utc()
    await _user_with_xp(session, "A", 300, ws + timedelta(hours=1))
    await _user_with_xp(session, "B", 200, ws + timedelta(hours=1))

    assert await refresh_ranks(session) == []  # birinchi hisoblash — xabar yo'q


async def test_overtaken_user_is_reported(session):
    ws = _week_start_utc()
    a = await _user_with_xp(session, "A", 300, ws + timedelta(hours=1))
    b = await _user_with_xp(session, "B", 200, ws + timedelta(hours=1))
    await refresh_ranks(session)

    session.add(XpLog(user_id=b.id, amount=500, source="t", created_at=ws + timedelta(hours=2)))
    await session.commit()

    dropped = await refresh_ranks(session)
    assert [(u.id, old, new) for u, old, new in dropped] == [(a.id, 1, 2)]


async def test_improving_rank_reports_nothing(session):
    ws = _week_start_utc()
    await _user_with_xp(session, "A", 300, ws + timedelta(hours=1))
    b = await _user_with_xp(session, "B", 200, ws + timedelta(hours=1))
    await refresh_ranks(session)

    session.add(XpLog(user_id=b.id, amount=500, source="t", created_at=ws + timedelta(hours=2)))
    await session.commit()
    dropped = await refresh_ranks(session)

    assert all(u.id != b.id for u, _, _ in dropped)
