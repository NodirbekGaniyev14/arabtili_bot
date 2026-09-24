"""K25.3 Oktagon mavsumi — haftalik reyting (faqat odam janglari), oylik mavsum yakuni va
yumshoq tiklash, admin digestdagi Oktagon bloki, /api/battle/season.

Oktagon — sof reyting: sovrin (VIP kuni, XP, muzlatkich) BERILMAYDI, top-3 faqat e'lon
qilinadi va `battle_awards` da tarix bo'lib qoladi."""

from datetime import datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from db.models import Battle, BattleAward, Meta, User, XpLog
from services import battle as bt
from services import battle_season as bs
from services.speaking_report import week_start_utc


@pytest.fixture(autouse=True)
def use_test_db(monkeypatch, session_factory):
    monkeypatch.setattr(bt, "SESSION_FACTORY", session_factory)


class FakeBot:
    def __init__(self):
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id, text, **kw):
        self.sent.append((chat_id, text))


# Sinovlar «o'tgan hafta» ichida yotishi uchun aniq lahza: chorshanba 12:00 (Toshkent).
NOW = datetime(2026, 9, 23, 7, 0)  # UTC → 12:00 Toshkent, seshanba
PREV_WEEK = week_start_utc(NOW) - timedelta(days=7)


async def _users(session, make_user, n: int) -> list[User]:
    users = [await make_user(f"O'quvchi{i}") for i in range(1, n + 1)]
    await session.commit()
    return users


def _battle(p1, p2, winner, d1, d2, at, *, mode="queue", bot_name=""):
    return Battle(
        level="A1",
        p1_id=p1,
        p2_id=p2,
        bot_name=bot_name,
        p1_score=100 if winner == 1 else 50,
        p2_score=100 if winner == 2 else 50,
        winner=winner,
        p1_delta=d1,
        p2_delta=d2,
        mode=mode,
        created_at=at,
    )


# ── kalendar ──


def test_season_keys_and_info():
    sep = bs.month_start_utc(datetime(2026, 9, 24, 3, 0))
    assert bs.season_key(sep) == "2026-09" and bs.season_label(sep) == "sentabr 2026"
    aug = bs.prev_month_start(sep)
    assert bs.season_key(aug) == "2026-08" and bs.season_label(aug) == "avgust 2026"
    # Yanvarning oldi — o'tgan yilning dekabri
    jan = bs.month_start_utc(datetime(2027, 1, 5))
    assert bs.season_key(bs.prev_month_start(jan)) == "2026-12"
    info = bs.season_info(datetime(2026, 9, 24, 3, 0))
    assert info["key"] == "2026-09" and info["ends_at"] == "01.10" and 1 <= info["days_left"] <= 8
    assert info["keep_pct"] == 50


def test_no_prize_api():
    """Sovrin mexanikasi butunlay olib tashlangan — kod qoldiqlari qolmasin."""
    assert not hasattr(bs, "prize") and not hasattr(bs, "prize_text")
    assert not hasattr(bs, "WEEK_PRIZE") and not hasattr(bs, "SEASON_PRIZE")


# ── haftalik jadval ──


@pytest.mark.asyncio
async def test_week_board_counts_only_human_battles(session, make_user):
    a, b, c = await _users(session, make_user, 3)
    at = PREV_WEEK + timedelta(days=1)
    session.add_all(
        [
            _battle(a.id, b.id, 1, 20, -10, at),
            _battle(a.id, b.id, 1, 20, -10, at, mode="friend"),
            _battle(b.id, c.id, 2, -10, 20, at),
            # Bot janglari — haftalik jadvalga KIRMAYDI
            _battle(a.id, None, 1, 10, 0, at, bot_name="Zayd"),
            _battle(a.id, None, 1, 10, 0, at, bot_name="Layla"),
            # O'tgan haftadan oldingi jang — davrdan tashqarida
            _battle(c.id, a.id, 1, 20, -10, PREV_WEEK - timedelta(days=2)),
        ]
    )
    await session.commit()

    board = await bs.week_board(session, PREV_WEEK, PREV_WEEK + timedelta(days=7))
    by_id = {r["user_id"]: r for r in board}
    assert by_id[a.id]["points"] == 40 and by_id[a.id]["games"] == 2 and by_id[a.id]["wins"] == 2
    assert by_id[b.id]["points"] == -30 and by_id[b.id]["games"] == 3 and by_id[b.id]["wins"] == 0
    assert by_id[c.id]["points"] == 20 and by_id[c.id]["games"] == 1
    assert [r["rank"] for r in board] == [1, 2, 3]
    assert [r["user_id"] for r in board] == [a.id, c.id, b.id]


@pytest.mark.asyncio
async def test_week_board_skips_demo_users(session, make_user):
    a = await make_user("Ali")
    demo = await make_user("Demo", is_demo=1)
    await session.commit()
    session.add(_battle(a.id, demo.id, 1, 20, -10, PREV_WEEK + timedelta(days=1)))
    await session.commit()
    board = await bs.week_board(session, PREV_WEEK, PREV_WEEK + timedelta(days=7))
    assert [r["user_id"] for r in board] == [a.id]


@pytest.mark.asyncio
async def test_week_summary_shape(session, make_user):
    a, b = await _users(session, make_user, 2)
    now = week_start_utc(NOW) + timedelta(days=2)
    session.add(_battle(a.id, b.id, 1, 20, -10, week_start_utc(NOW) + timedelta(hours=3)))
    await session.commit()
    s = await bs.week_summary(session, a.id, now)
    assert s["me"]["rank"] == 1 and s["me"]["points"] == 20
    assert s["hours_left"] > 0 and len(s["top"]) == 2
    assert "prizes" not in s and s["min_players"] == bs.WEEK_MIN_PLAYERS
    other = await bs.week_summary(session, 999_999, now)
    assert other["me"]["rank"] == 0 and other["me"]["points"] == 0


# ── haftalik yakun ──


@pytest.mark.asyncio
async def test_run_week_records_top3_and_announces(session, make_user, session_factory):
    users = await _users(session, make_user, 4)
    a, b, c, d = users
    at = PREV_WEEK + timedelta(days=2)
    session.add_all(
        [
            _battle(a.id, b.id, 1, 20, -10, at),
            _battle(a.id, c.id, 1, 20, -10, at),
            _battle(c.id, d.id, 1, 20, -10, at),
            _battle(b.id, d.id, 1, 20, -10, at),
        ]
    )
    await session.commit()

    fake = FakeBot()
    res = await bs.run_week(fake, NOW)
    assert res["players"] == 4 and [w["rank"] for w in res["winners"]] == [1, 2, 3]
    assert res["winners"][0]["user_id"] == a.id and res["winners"][0]["points"] == 40

    async with session_factory() as s2:
        awards = (await s2.execute(select(BattleAward).order_by(BattleAward.rank))).scalars().all()
        assert len(awards) == 3 and {aw.period for aw in awards} == {"week"}
        assert awards[0].period_key == res["key"] and awards[0].points == 40
        # SOVRIN YO'Q: VIP, XP va muzlatkich tegilmaydi
        winner = await s2.get(User, a.id)
        assert winner.vip_until is None and winner.streak_freezes == 2  # standart qiymat o'zgarmadi
        assert (await s2.execute(select(XpLog))).scalars().all() == []
        assert [aw.vip_days for aw in awards] == [0, 0, 0] and [aw.xp for aw in awards] == [0, 0, 0]

    # Hamma ishtirokchiga e'lon ketdi, g'oliblar ro'yxati bilan
    assert len(fake.sent) == 4
    assert "Haftalik Oktagon yakunlandi" in fake.sent[0][1] and "O'quvchi1" in fake.sent[0][1]
    assert "VIP" not in fake.sent[0][1] and "🎁" not in fake.sent[0][1]

    # Ikkinchi chaqiruv — marker bor, takror sovrin yo'q
    fake2 = FakeBot()
    assert await bs.run_week(fake2, NOW) is None
    assert fake2.sent == []


@pytest.mark.asyncio
async def test_run_week_needs_min_players(session, make_user, session_factory):
    a, b = await _users(session, make_user, 2)
    session.add(_battle(a.id, b.id, 1, 20, -10, PREV_WEEK + timedelta(days=1)))
    await session.commit()

    fake = FakeBot()
    res = await bs.run_week(fake, NOW)
    assert res["players"] == 2 and res["winners"] == [] and fake.sent == []
    async with session_factory() as s2:
        assert (await s2.execute(select(BattleAward))).scalars().all() == []
        marker = (await s2.execute(select(Meta).where(Meta.key == bs.WEEK_MARKER))).scalar_one()
        assert marker.value == res["key"]


# ── mavsum yakuni ──


@pytest.mark.asyncio
async def test_run_season_records_and_soft_reset(session, make_user, session_factory):
    users = await _users(session, make_user, 5)
    for i, u in enumerate(users):
        u.battle_points = 500 - i * 100  # 500, 400, 300, 200, 100
        u.battle_games, u.battle_wins = 20, 12
        session.add(u)
    await session.commit()

    fake = FakeBot()
    now = datetime(2026, 10, 1, 5, 0)  # 10:00 Toshkent, 1-oktabr
    res = await bs.run_season(fake, now)
    assert res["key"] == "2026-09" and res["label"] == "sentabr 2026" and res["reset"] == 5
    assert [w["user_id"] for w in res["winners"]] == [users[0].id, users[1].id, users[2].id]

    async with session_factory() as s2:
        rows = (await s2.execute(select(User).order_by(User.id))).scalars().all()
        assert [u.battle_points for u in rows] == [250, 200, 150, 100, 50]  # yumshoq tiklash
        assert {u.battle_games for u in rows} == {20} and {u.battle_wins for u in rows} == {12}
        aw = (await s2.execute(select(BattleAward).order_by(BattleAward.rank))).scalars().all()
        assert [x.rank for x in aw] == [1, 2, 3] and [x.vip_days for x in aw] == [0, 0, 0]
        assert aw[0].points == 500 and aw[0].period == "season"
        assert all(u.vip_until is None for u in rows)  # sovrin yo'q
    assert len(fake.sent) == 5 and "mavsumi yakunlandi" in fake.sent[0][1]
    assert await bs.run_season(FakeBot(), now) is None


@pytest.mark.asyncio
async def test_run_season_without_min_players_keeps_points(session, make_user, session_factory):
    users = await _users(session, make_user, 2)
    for u in users:
        u.battle_points, u.battle_games = 300, 5
        session.add(u)
    await session.commit()

    res = await bs.run_season(FakeBot(), datetime(2026, 10, 1, 5, 0))
    assert res["winners"] == [] and res["reset"] == 0
    async with session_factory() as s2:
        assert [u.battle_points for u in (await s2.execute(select(User))).scalars().all()] == [300, 300]


@pytest.mark.asyncio
async def test_past_awards(session, make_user, session_factory):
    a, b = await _users(session, make_user, 2)
    session.add_all(
        [
            BattleAward(user_id=a.id, period="week", period_key="2026-09-07", rank=1, points=10),
            BattleAward(user_id=b.id, period="week", period_key="2026-09-14", rank=1, points=80, games=6, wins=5),
            BattleAward(user_id=a.id, period="week", period_key="2026-09-14", rank=2, points=40, games=5, wins=3),
        ]
    )
    await session.commit()
    last = await bs.past_awards(session, "week")
    assert [x["rank"] for x in last] == [1, 2] and last[0]["name"] == "O'quvchi2"
    assert last[0]["period_key"] == "2026-09-14" and last[0]["wins"] == 5
    assert await bs.past_awards(session, "season") == []


# ── API va digest ──


@pytest.mark.asyncio
async def test_api_season_endpoint(session, make_user):
    from db.session import get_session
    from main import app
    from services.telegram_auth import get_current_user

    a, b = await _users(session, make_user, 2)
    session.add(_battle(a.id, b.id, 1, 20, -10, week_start_utc(datetime.utcnow()) + timedelta(minutes=5)))
    session.add(BattleAward(user_id=b.id, period="season", period_key="2026-08", rank=1, points=900, games=30, wins=22))
    await session.commit()

    async def _session():
        yield session

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: a
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            r = (await c.get("/api/battle/season")).json()
    finally:
        app.dependency_overrides.clear()
    assert r["season"]["label"] and r["season"]["days_left"] >= 0
    assert r["week"]["me"]["rank"] == 1 and r["week"]["me"]["points"] == 20
    assert r["last_season"][0]["name"] == "O'quvchi2" and r["last_week"] == []
    assert "season_prizes" not in r and "prizes" not in r["week"]


@pytest.mark.asyncio
async def test_digest_has_oktagon_block(session, make_user):
    from services import admin_digest

    from services.speaking_report import week_key

    a, b = await _users(session, make_user, 2)
    prev_monday = week_start_utc(datetime.utcnow()) - timedelta(days=7)
    at = prev_monday + timedelta(days=1)  # o'tgan hafta ichida
    session.add_all(
        [
            _battle(a.id, b.id, 1, 20, -10, at),
            _battle(a.id, b.id, 1, 20, -10, at, mode="friend"),
            _battle(a.id, None, 1, 10, 0, at, bot_name="Zayd"),
        ]
    )
    session.add(
        BattleAward(
            user_id=a.id,
            period="week",
            period_key=week_key(prev_monday),
            rank=1,
            points=40,
        )
    )
    await session.commit()
    text = await admin_digest.build(session)
    assert "⚔️ <b>Oktagon</b>" in text
    assert "Janglar: 3" in text and "odam bilan: 67%" in text and "do'st havolasi: 1" in text
    assert "jangchilar: 2" in text and "/oktagon" in text
