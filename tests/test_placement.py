"""Daraja aniqlash testi — bosqichlar A0 dan B2 gacha (K15.5)."""

import pytest

from services import placement as pl


def test_tiers_cover_every_level():
    from services.course import LEVELS

    assert pl.TIERS == LEVELS == ["A0", "A1", "A2", "B1", "B2"]


def test_every_tier_has_five_questions():
    for tier in pl.TIERS:
        qs = pl.tier_questions(tier)
        assert len(qs) == 5, f"{tier}: 5 savol bo'lishi kerak"
        assert pl.tier_title(tier) != tier, f"{tier}: title_uz yo'q"


def test_tier_answers_are_among_options():
    for tier in pl.TIERS:
        for q in pl.tier_questions(tier):
            assert q["answer"] in q["options"], f"{tier}: {q['q_uz']}"
            assert len(set(q["options"])) == len(q["options"])
            assert q["explain_uz"]


def test_total_questions():
    assert pl.total_questions() == 25


# ── Adaptiv oqim ──


def test_next_tier_walks_up():
    results = {}
    for tier in pl.TIERS:
        assert pl.next_tier(results) == tier
        results[tier] = True
    assert pl.next_tier(results) is None


def test_test_stops_after_first_failure():
    results = {"A0": True, "A1": True, "A2": False}
    assert pl.next_tier(results) is None
    assert pl.decide_level(results) == "A2"


@pytest.mark.parametrize(
    "passed,level",
    [
        ([], "A0"),
        (["A0"], "A1"),
        (["A0", "A1"], "A2"),
        (["A0", "A1", "A2"], "B1"),
        (["A0", "A1", "A2", "B1"], "B2"),
        (["A0", "A1", "A2", "B1", "B2"], "B2"),
    ],
)
def test_decide_level(passed, level):
    assert pl.decide_level({t: True for t in passed}) == level


def test_all_passed_reason_mentions_b2():
    results = {t: True for t in pl.TIERS}
    assert "B2" in pl.level_reason("B2", results)


def test_reason_exists_for_every_outcome():
    results = {}
    for tier in pl.TIERS:
        level = pl.decide_level(results)
        assert pl.level_reason(level, results)
        results[tier] = True
    assert pl.level_reason(pl.decide_level(results), results)


def test_version_not_bumped():
    """B2 bosqichi qo'shildi, ammo eski foydalanuvchilar qayta test topshirmaydi."""
    assert pl.PLACEMENT_VERSION == 2


# ── O'tish chegarasi ──


def test_pass_threshold_is_four_of_five():
    assert pl.tier_passed(4, 5) is True
    assert pl.tier_passed(3, 5) is False
