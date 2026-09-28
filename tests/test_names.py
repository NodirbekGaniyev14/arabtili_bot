"""K27.5 — xabarlardagi ism: HTML-xavfsiz, harfsiz ism o'rniga zaxira, arabcha ismdan keyin LRM."""

from datetime import datetime, timedelta

from services import admin_digest, battle_season, weekly
from services.names import LRM, admin_show, show


def test_show_escapes_and_falls_back():
    assert show("Ali <3 & Vali") == "Ali &lt;3 &amp; Vali" + LRM
    assert show("...") == "O'rganuvchi" + LRM and show("🔥🔥") == "O'rganuvchi" + LRM and show(None) == "O'rganuvchi" + LRM
    assert show("🇸🇦 بحرزبيك") == "🇸🇦 بحرزبيك" + LRM
    assert admin_show("...", "ali_uz", 5) == "@ali_uz" + LRM
    assert admin_show("", "", 12345) == "ID 12345" + LRM
    assert admin_show("Шерзод", "x", 1) == "Шерзод" + LRM


def test_announcements_use_safe_names():
    t = weekly.announcement_text("week", "21.09 — 27.09", [(1, "<b>Ali</b>", 500, 1), (2, "...", 400, 2)], None, 10)
    assert "&lt;b&gt;Ali&lt;/b&gt;" in t and "O'rganuvchi" in t and "<b>Ali</b>" not in t
    w = [{"rank": 1, "name": "A&B", "points": 690, "wins": 5, "games": 7}]
    assert "A&amp;B" + LRM in battle_season.winners_text("week", "21.09 — 27.09", w, None, 12)


async def test_digest_names_safe(session, make_user):
    from db.models import BattleAward, WeeklyAward

    now = datetime(2026, 9, 28, 6, 0)
    prev_monday = admin_digest.week_start_utc(now) - timedelta(days=7)
    a = await make_user("...", username="dots")
    b = await make_user("🇸🇦 بحرزبيك")
    c = await make_user("x<y")
    key = admin_digest.week_key(prev_monday)
    session.add_all(
        [
            WeeklyAward(user_id=a.id, period="week", week_start=key, rank=1, weekly_xp=5021),
            WeeklyAward(user_id=b.id, period="week", week_start=key, rank=2, weekly_xp=3454),
            BattleAward(user_id=c.id, period="week", period_key=key, rank=1, points=690, vip_days=0, xp=0),
        ]
    )
    await session.commit()
    text = await admin_digest.build(session, now)
    assert "🥇 @dots" + LRM + " (5021)" in text
    assert "🇸🇦 بحرزبيك" + LRM + " (3454)" in text
    assert "x&lt;y" + LRM + " (690)" in text and "x<y" not in text
