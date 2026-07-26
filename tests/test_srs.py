"""SRS (SM-2 soddalashtirilgan) — interval, ease va qayta ko'rish sanasi."""

from datetime import date, timedelta

import pytest

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
