"""Liga mexanikasi — haftalik ko'tarilish va tushish."""

from datetime import timedelta

import pytest

from db.models import User, XpLog
from services.league import (
    LEAGUE_ORDER,
    MIN_FOR_RELEGATION,
    MIN_XP_TO_PROMOTE,
    PROMOTE_TOP,
    RELEGATE_BOTTOM,
    _shift,
    _week_start_utc,
    apply_league_movement,
    league_by_id,
)


async def _member(session, name, xp, league, when):
    u = User(tg_id=abs(hash(name)) % 10_000_000, name=name, league_id=league)
    session.add(u)
    await session.flush()
    if xp:
        session.add(XpLog(user_id=u.id, amount=xp, source="t", created_at=when))
    await session.commit()
    return u


# ── Yordamchilar ──


def test_shift_clamps_at_edges():
    assert _shift("bronze", -1) == "bronze"      # pastdan pastga yo'q
    assert _shift("emerald", +1) == "emerald"    # yuqoridan yuqoriga yo'q
    assert _shift("bronze", +1) == "silver"
    assert _shift("gold", -1) == "silver"


def test_league_by_id_falls_back_to_bronze():
    assert league_by_id("")["id"] == "bronze"
    assert league_by_id("yo'q-liga")["id"] == "bronze"
    assert league_by_id("gold")["name"] == "Oltin"


# ── Ko'tarilish ──


async def test_top_three_promote(session):
    ws = _week_start_utc()
    for i, xp in enumerate([500, 400, 300, 200, 100]):
        await _member(session, f"B{i}", xp, "bronze", ws + timedelta(hours=1))

    moved = await apply_league_movement(session, ws)
    promoted = [u.name for u, old, new in moved if new == "silver"]
    assert len(promoted) == PROMOTE_TOP
    assert promoted == ["B0", "B1", "B2"]


async def test_low_xp_does_not_promote(session):
    """Faolligi deyarli yo'q odam 'g'olib' bo'lib ko'tarilmasin."""
    ws = _week_start_utc()
    await _member(session, "Sust", MIN_XP_TO_PROMOTE - 1, "bronze", ws + timedelta(hours=1))
    moved = await apply_league_movement(session, ws)
    assert moved == []


async def test_zero_xp_does_not_promote(session):
    ws = _week_start_utc()
    await _member(session, "Nol", 0, "bronze", ws)
    assert await apply_league_movement(session, ws) == []


async def test_emerald_cannot_promote_further(session):
    ws = _week_start_utc()
    await _member(session, "Cho'qqi", 5000, "emerald", ws + timedelta(hours=1))
    moved = await apply_league_movement(session, ws)
    assert moved == []


# ── Tushish ──


async def test_no_relegation_in_small_league(session):
    """3 kishilik ligada oxirgi o'rin jazoga loyiq emas."""
    ws = _week_start_utc()
    for i, xp in enumerate([300, 200, 10]):
        await _member(session, f"S{i}", xp, "silver", ws + timedelta(hours=1))

    moved = await apply_league_movement(session, ws)
    assert all(new != "bronze" for _, _, new in moved)


async def test_bottom_relegates_in_large_league(session):
    ws = _week_start_utc()
    xps = [900, 800, 700, 600, 500, 400, 30, 20, 10]  # 9 kishi
    assert len(xps) >= MIN_FOR_RELEGATION
    for i, xp in enumerate(xps):
        await _member(session, f"S{i}", xp, "silver", ws + timedelta(hours=1))

    moved = await apply_league_movement(session, ws)
    relegated = [u.name for u, _, new in moved if new == "bronze"]
    assert len(relegated) == RELEGATE_BOTTOM
    assert set(relegated) == {"S6", "S7", "S8"}


async def test_bronze_cannot_relegate(session):
    ws = _week_start_utc()
    for i in range(MIN_FOR_RELEGATION + 1):
        await _member(session, f"B{i}", 10 * (i + 1), "bronze", ws + timedelta(hours=1))

    moved = await apply_league_movement(session, ws)
    assert all(new != _shift("bronze", -1) or new == "bronze" for _, _, new in moved)
    assert all(old != "bronze" or LEAGUE_ORDER.index(new) > 0 for _, old, new in moved)


async def test_user_is_not_both_promoted_and_relegated(session):
    ws = _week_start_utc()
    for i, xp in enumerate([900, 800, 700, 600, 500, 400, 300, 200]):
        await _member(session, f"S{i}", xp, "silver", ws + timedelta(hours=1))

    moved = await apply_league_movement(session, ws)
    ids = [u.id for u, _, _ in moved]
    assert len(ids) == len(set(ids)), "bir odam ikki marta ko'chirilgan"


# ── Doimiylik ──


async def test_movement_persists_to_db(session):
    ws = _week_start_utc()
    u = await _member(session, "Yulduz", 900, "bronze", ws + timedelta(hours=1))
    await _member(session, "Ikki", 100, "bronze", ws + timedelta(hours=1))

    await apply_league_movement(session, ws)
    await session.refresh(u)
    assert u.league_id == "silver"


async def test_leagues_are_independent(session):
    """Bronza va kumush alohida saraladi — aralashmaydi."""
    ws = _week_start_utc()
    await _member(session, "BronzaTop", 100, "bronze", ws + timedelta(hours=1))
    await _member(session, "KumushPast", 5000, "silver", ws + timedelta(hours=1))

    moved = await apply_league_movement(session, ws)
    by_name = {u.name: (old, new) for u, old, new in moved}
    assert by_name["BronzaTop"] == ("bronze", "silver")
    assert by_name["KumushPast"] == ("silver", "gold")
