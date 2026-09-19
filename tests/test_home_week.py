"""K19.1 — bosh sahifa: oxirgi 7 kun diagrammasi va «Bugun» ro'yxati bayroqlari."""

from datetime import date, datetime, timedelta

import pytest

from db.models import UserWord, XpLog
from services import stats as st


def test_week_series_buckets_by_local_day():
    today = date(2026, 9, 19)  # Toshkent = UTC+5
    rows = [
        (datetime(2026, 9, 19, 3, 0), 10, "lesson:a0-01"),      # 08:00 bugun
        (datetime(2026, 9, 19, 5, 0), 5, "daily:2026-09-19"),   # 10:00 bugun (speaking)
        (datetime(2026, 9, 18, 20, 50), 6, "review"),           # UTC kecha 20:50 = bugun 01:50 Toshkent
        (datetime(2026, 9, 18, 18, 0), 30, "checkpoint:a0-16"),  # 23:00 kecha
        (datetime(2026, 9, 13, 6, 0), 8, "drill:k"),             # 7-kun (eng eski)
        (datetime(2026, 9, 12, 6, 0), 99, "lesson:x"),           # 8 kun oldin — tashqarida
    ]
    week = st.week_series(rows, today)
    assert len(week) == 7 and week[0]["day"] == "2026-09-13" and week[-1]["day"] == "2026-09-19"
    assert week[-1] == {"day": "2026-09-19", "xp": 21, "lessons": 1, "speaking": 1}
    assert week[-2] == {"day": "2026-09-18", "xp": 30, "lessons": 1, "speaking": 0}
    assert week[0] == {"day": "2026-09-13", "xp": 8, "lessons": 0, "speaking": 1}
    assert sum(c["xp"] for c in week) == 59, "8 kun oldingi XP kirmaydi"


@pytest.mark.asyncio
async def test_user_stats_today_flags(session, make_user, monkeypatch):
    u = await make_user("Nodir")
    today = date(2026, 9, 19)
    monkeypatch.setattr(st, "_today", lambda: today)
    now = datetime(2026, 9, 19, 6, 0)  # 11:00 Toshkent
    s = await st.user_stats(session, u.id)
    assert s["today"] == {"lesson_done": False, "review_done": True, "speaking_done": False, "new_words": 0, "new_words_goal": st.NEW_WORDS_GOAL}
    assert len(s["week"]) == 7 and all(c["xp"] == 0 for c in s["week"])

    session.add(XpLog(user_id=u.id, amount=10, source="lesson:a0-01", created_at=now))
    session.add(XpLog(user_id=u.id, amount=7, source="drill:abc", created_at=now))
    for i in range(3):
        session.add(UserWord(user_id=u.id, ar=f"كلمة{i}", due_date="2026-09-19", created_at=now))
    session.add(UserWord(user_id=u.id, ar="قديم", due_date="2026-09-19", created_at=now - timedelta(days=2)))
    await session.flush()
    s = await st.user_stats(session, u.id)
    t = s["today"]
    assert t["lesson_done"] and t["speaking_done"] and t["new_words"] == 3
    assert t["review_done"] is False, "4 ta karta bugun takrorlanishi kerak, «review» XP yo'q"
    assert s["week"][-1]["xp"] == 17 and s["week"][-1]["lessons"] == 1 and s["due_count"] == 4
    session.add(XpLog(user_id=u.id, amount=3, source="review", created_at=now))
    await session.flush()
    assert (await st.user_stats(session, u.id))["today"]["review_done"] is True
