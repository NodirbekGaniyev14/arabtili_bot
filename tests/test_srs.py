"""SRS (SM-2 soddalashtirilgan) — interval, ease va qayta ko'rish sanasi."""

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from db.models import UserWord
from services.srs import MAX_EASE, MAX_INTERVAL, MIN_EASE, apply_grade
from services.stats import _today


def card(**kw) -> UserWord:
    """Bazadan yuklangan kartaga o'xshash obyekt (ustun standartlari qo'llangan)."""
    base = dict(
        user_id=1,
        ar="كِتَاب",
        uz="kitob",
        due_date=_today().isoformat(),
        reps=0,
        lapses=0,
        interval_days=0,
        ease=2.5,
        translit="",
        audio="",
        kind="word",
        card_type="word",
    )
    base.update(kw)
    return UserWord(**base)


def due_in(word: UserWord) -> int:
    return (date.fromisoformat(word.due_date) - _today()).days


# ── Birinchi ko'rish ──


def test_new_card_good_gives_one_day():
    w = card(reps=0, interval_days=0)
    apply_grade(w, "good")
    assert w.interval_days == 1
    assert due_in(w) == 1
    assert w.reps == 1


def test_new_card_easy_jumps_three_days():
    w = card(reps=0, interval_days=0)
    apply_grade(w, "easy")
    assert w.interval_days == 3


def test_new_card_hard_gives_one_day():
    w = card(reps=0, interval_days=0)
    apply_grade(w, "hard")
    assert w.interval_days == 1


# ── "Again" — xato javob ──


def test_again_resets_progress_and_counts_lapse():
    w = card(reps=5, interval_days=30, lapses=1, ease=2.5)
    apply_grade(w, "again")
    assert w.reps == 0
    assert w.interval_days == 0
    assert w.lapses == 2
    assert w.ease == pytest.approx(2.3)
    assert due_in(w) == 0  # bugun yana ko'rsatiladi


def test_ease_never_below_minimum():
    w = card(reps=3, ease=MIN_EASE)
    for _ in range(5):
        apply_grade(w, "again")
    assert w.ease == MIN_EASE


# ── Intervalning o'sishi ──


def test_good_multiplies_by_ease():
    w = card(reps=2, interval_days=10, ease=2.5)
    apply_grade(w, "good")
    assert w.interval_days == 25


def test_easy_grows_faster_than_good():
    a = card(reps=2, interval_days=10, ease=2.5)
    b = card(reps=2, interval_days=10, ease=2.5)
    apply_grade(a, "good")
    apply_grade(b, "easy")
    assert b.interval_days > a.interval_days


def test_hard_grows_slower_than_good():
    a = card(reps=2, interval_days=10, ease=2.5)
    b = card(reps=2, interval_days=10, ease=2.5)
    apply_grade(a, "good")
    apply_grade(b, "hard")
    assert b.interval_days < a.interval_days


def test_easy_raises_ease_but_capped():
    w = card(reps=2, interval_days=5, ease=MAX_EASE)
    apply_grade(w, "easy")
    assert w.ease == MAX_EASE


def test_interval_capped_at_maximum():
    w = card(reps=10, interval_days=MAX_INTERVAL, ease=MAX_EASE)
    apply_grade(w, "easy")
    assert w.interval_days == MAX_INTERVAL
    assert due_in(w) == MAX_INTERVAL


# ── Uzoq muddatli xatti-harakat ──


def test_repeated_good_reaches_month_scale():
    w = card(reps=0, interval_days=0, ease=2.5)
    for _ in range(5):
        apply_grade(w, "good")
    assert w.interval_days > 30
    assert w.reps == 5


def test_lapse_then_recovery_starts_over():
    w = card(reps=4, interval_days=40, ease=2.5)
    apply_grade(w, "again")
    apply_grade(w, "good")
    assert w.interval_days == 1  # noldan boshlanadi
    assert w.ease < 2.5  # lekin ease pasaygancha qoladi


def test_due_date_is_always_iso_string():
    w = card()
    apply_grade(w, "good")
    assert date.fromisoformat(w.due_date) >= _today()


# ── Kartoteka matni eskirgan bo'lsa joriy kontentdan yangilanadi ──


def test_refresh_card_updates_stale_translation():
    from services.srs import content_cards, refresh_card

    exact, _ = content_cards()
    assert "جَارٌ" in exact and exact["جَارٌ"]["uz"] == "qo'shni"
    w = card(ar="جَارٌ", uz="qo'shnil", translit="", audio="")
    assert refresh_card(w) is True
    assert w.uz == "qo'shni" and w.translit == "jār" and w.audio == "b1/jar.mp3"
    assert refresh_card(w) is False, "ikkinchi marta o'zgarish yo'q"
    # O'zak kartasi va noma'lum so'z — tegilmaydi
    r = card(ar="ج و ر", uz="qo'shni bo'lmoq → ...", kind="root", card_type="root")
    assert refresh_card(r) is False
    u = card(ar="كلمةغيرموجودة", uz="x")
    assert refresh_card(u) is False and u.uz == "x"


@pytest.mark.asyncio
async def test_review_returns_fresh_translation(session, make_user):
    import httpx

    from db.session import get_session
    from main import app
    from services.telegram_auth import get_current_user

    user = await make_user("Srs")
    session.add(UserWord(user_id=user.id, ar="جَارٌ", uz="qo'shnil", kind="word", due_date="2000-01-01"))
    await session.commit()

    async def _session():
        yield session

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            d = (await c.get("/api/review")).json()
    finally:
        app.dependency_overrides.clear()
    assert [x["uz"] for x in d["cards"] if x["ar"] == "جَارٌ"] == ["qo'shni"]
    row = (await session.execute(select(UserWord).where(UserWord.user_id == user.id))).scalar_one()
    assert row.uz == "qo'shni", "DB ham yangilangan"
