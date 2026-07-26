"""Ma'lumotnoma — grammatika va lug'at qidiruvi."""

import pytest

from services.reference import (
    normalize,
    reference_stats,
    search_grammar,
    search_vocab,
)


# ── Normalizatsiya ──


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("KITOB", "kitob"),
        ("kit'ob", "kitob"),
        ("  ikki   probel ", "ikki probel"),
        ("كِتَاب", "كتاب"),      # harakatlar tushadi
        ("أحمد", "احمد"),        # hamzali alif → alif
        ("إسلام", "اسلام"),
    ],
)
def test_normalize(raw, expected):
    assert normalize(raw) == expected


# ── Statistika ──


def test_stats_are_nonempty():
    s = reference_stats()
    assert s["grammar_points"] > 100
    assert s["vocab_words"] > 800


# ── Lug'at qidiruvi ──


def test_empty_query_returns_everything():
    r = search_vocab("")
    assert r["total"] == reference_stats()["vocab_words"]


def test_uzbek_search_finds_word():
    r = search_vocab("kitob")
    assert r["total"] >= 1
    assert any("كتاب" in normalize(i["ar"]) for i in r["items"])


def test_arabic_search_ignores_harakat():
    """Foydalanuvchi harakatsiz yozadi — baribir topilsin."""
    with_h = search_vocab("كِتَاب")["total"]
    without_h = search_vocab("كتاب")["total"]
    assert with_h == without_h > 0


def test_root_search_works():
    r = search_vocab("ك ت ب")
    assert r["total"] >= 3


def test_translit_search_works():
    r = search_vocab("kitāb")
    assert r["total"] >= 1


def test_level_filter_narrows_results():
    all_words = search_vocab("")["total"]
    a0 = search_vocab("", "A0")["total"]
    assert 0 < a0 < all_words
    assert all(i["level"] == "A0" for i in search_vocab("", "A0")["items"])


def test_nonsense_query_returns_nothing():
    assert search_vocab("zzzqqqxyz")["total"] == 0


def test_pagination_does_not_repeat():
    p1 = search_vocab("", limit=20, offset=0)["items"]
    p2 = search_vocab("", limit=20, offset=20)["items"]
    assert len(p1) == len(p2) == 20
    assert {i["ar"] for i in p1}.isdisjoint({i["ar"] for i in p2})


def test_duplicate_words_merged_with_lesson_list():
    """Bir so'z bir necha darsda uchrasa — bitta yozuv, lessons ro'yxati bilan."""
    items = search_vocab("")["items"]
    multi = [i for i in search_vocab("kitob")["items"] if len(i["lessons"]) > 1]
    assert all(len(i["lessons"]) >= 1 for i in items)
    assert multi, "hech bo'lmasa bitta so'z bir necha darsda bo'lishi kerak"


# ── Grammatika qidiruvi ──


def test_grammar_covers_all_levels():
    levels = {g["level"] for g in search_grammar("")["items"]}
    assert levels == {"A0", "A1", "A2", "B1"}


def test_grammar_search_by_uzbek_term():
    r = search_grammar("majhul")
    assert r["total"] >= 3
    assert all(
        "majhul" in (g["explanation_uz"] + g["lesson_title"]).lower()
        or "majhul" in normalize(g["point_ar"])
        for g in r["items"]
    )


def test_grammar_level_filter():
    r = search_grammar("", "A0")
    assert r["total"] > 0
    assert all(g["level"] == "A0" for g in r["items"])


def test_grammar_entries_have_required_fields():
    for g in search_grammar("", "A1")["items"][:5]:
        assert g["lesson_id"]
        assert g["explanation_uz"]
        assert isinstance(g["table"], list)
        assert isinstance(g["common_mistakes_uz"], list)
