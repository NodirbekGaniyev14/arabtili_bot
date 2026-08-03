"""Lug'at bo'limi — baza, qidiruv, kunlik to'plam, SRS (K16).

Reja: docs/VOCAB_PLAN.md. Bu testlar lug'at bazasi to'g'ri tuzilganini va
darsdagi so'zlar bilan TAKRORLANMASLIGINI kafolatlaydi.
"""

import json
from pathlib import Path

import pytest

from services import vocab as vc
from services.reference import normalize

ROOT = Path(__file__).resolve().parent.parent
VOCAB_DIR = ROOT / "content" / "vocab"
AUDIO_DIR = ROOT / "webapp" / "public" / "audio"


# ── Fayl tuzilmasi ──


def test_every_level_has_a_file():
    for lv in vc.LEVELS:
        path = VOCAB_DIR / f"{lv.lower()}.json"
        assert path.exists(), f"{path} yo'q"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["level"] == lv
        assert isinstance(data["words"], list)


def test_targets_sum_to_six_thousand():
    assert sum(vc.TARGETS.values()) == 6000


def test_thirty_six_themes():
    assert len(vc.THEMES) == 36
    assert all(slug and title for slug, title in vc.THEMES.items())


# ── Baza mazmuni ──


def test_no_duplicate_words():
    seen: dict[str, str] = {}
    for w in vc.all_words():
        key = normalize(w["ar"])
        assert key not in seen, f"{w['ar']} ikki marta: {seen.get(key)} va {w['id']}"
        seen[key] = w["id"]


def test_vocab_base_does_not_repeat_lesson_words():
    """Darsda bor so'z bazaga qo'shilmasin — bitta so'z bir joyda."""
    from services.reference import vocab_entries

    in_lessons = {normalize(e["ar"]) for e in vocab_entries()}
    for lv in vc.LEVELS:
        for w in vc.load_level(lv):
            assert normalize(w["ar"]) not in in_lessons, (
                f"{w['ar']} ({lv}) darsda ham bor"
            )


def test_word_fields_and_values():
    for w in vc.all_words():
        assert w["ar"] and w["uz"], w["id"]
        assert w["level"] in vc.LEVELS
        if w.get("theme"):
            assert w["theme"] in vc.THEMES, f"{w['id']}: theme={w['theme']}"


def test_base_words_use_canonical_pos():
    """Yangi bazada turkum atamalari bir xil (darslarda tarixan aralash)."""
    for lv in vc.LEVELS:
        for w in vc.load_level(lv):
            assert w["pos"] in vc.POS, f"{w['id']}: pos={w['pos']}"


def test_base_words_have_example_and_audio():
    for lv in vc.LEVELS:
        for w in vc.load_level(lv):
            assert w["example_ar"] and w["example_uz"], f"{w['id']}: misol yo'q"
            assert w["audio"].startswith("vocab/"), f"{w['id']}: audio nomi noto'g'ri"


def test_base_audio_files_exist():
    missing = [
        w["audio"]
        for lv in vc.LEVELS
        for w in vc.load_level(lv)
        if not (AUDIO_DIR / w["audio"]).exists()
    ]
    assert not missing, f"audio fayllari yo'q: {missing[:10]}"


def test_ranks_are_unique():
    ranks = [w["rank"] for lv in vc.LEVELS for w in vc.load_level(lv)]
    assert len(ranks) == len(set(ranks))
    assert all(1 <= r <= 6000 for r in ranks)


# ── Qidiruv ──


def test_search_without_query_returns_everything():
    assert vc.search()["total"] == len(vc.all_words())


def test_search_finds_lesson_word_by_uzbek():
    r = vc.search("kitob")
    assert r["total"] > 0
    assert any("kitob" in w["uz"].lower() for w in r["items"])


def test_search_ignores_harakat():
    """Harakatsiz yozilgan so'z ham topiladi."""
    plain = vc.search("كتاب")
    assert plain["total"] > 0


def test_search_level_filter():
    r = vc.search(level="A0")
    assert r["total"] > 0
    assert all(w["level"] == "A0" for w in r["items"])


def test_search_pagination():
    first = vc.search(limit=5)
    second = vc.search(limit=5, offset=5)
    assert first["total"] == second["total"]
    assert {w["id"] for w in first["items"]} & {w["id"] for w in second["items"]} == set()


# ── Mavzular va statistika ──


def test_theme_list_covers_all_themes():
    items = vc.theme_list()
    assert len(items) == 36
    assert all(set(i) == {"slug", "title_uz", "total"} for i in items)


def test_stats_shape():
    s = vc.stats()
    assert s["goal"] == 6000
    assert s["total"] == len(vc.all_words())
    assert [row["level"] for row in s["levels"]] == list(vc.LEVELS)
    assert all(row["target"] == vc.TARGETS[row["level"]] for row in s["levels"])


# ── Kunlik to'plam ──


def test_daily_skips_known_words():
    words = vc.all_words()
    known = {w["ar"] for w in words[:5]}
    daily = vc.daily_set(known, n=10)
    assert len(daily) == 10
    assert not ({normalize(w["ar"]) for w in daily} & {normalize(a) for a in known})


def test_daily_respects_level():
    daily = vc.daily_set(set(), level="A0", n=5)
    assert all(w["level"] == "A0" for w in daily)


def test_word_by_ar_ignores_harakat():
    w = vc.all_words()[0]
    assert vc.word_by_ar(w["ar"]) is w
    stripped = normalize(w["ar"])
    assert vc.word_by_ar(stripped) is w
    assert vc.word_by_ar("لاشيءهنا") is None


# ── API ──


@pytest.mark.asyncio
async def test_learn_adds_words_to_srs(session, make_user):
    from db.models import UserWord
    from sqlalchemy import select

    user = await make_user()
    words = vc.all_words()[:3]
    from api.routes import LearnBody, vocab_learn

    res = await vocab_learn(LearnBody(words=[w["ar"] for w in words]), user, session)
    assert res["added"] == 3

    rows = (
        await session.execute(select(UserWord).where(UserWord.user_id == user.id))
    ).scalars().all()
    assert {r.ar for r in rows} == {w["ar"] for w in words}
    assert all(r.deck == "msa" and r.card_type == "word" for r in rows)

    # Ikkinchi marta qo'shilmaydi
    again = await vocab_learn(LearnBody(words=[w["ar"] for w in words]), user, session)
    assert again["added"] == 0


@pytest.mark.asyncio
async def test_stats_counts_learned(session, make_user):
    from api.routes import LearnBody, vocab_learn, vocab_stats

    user = await make_user()
    words = vc.all_words()[:2]
    await vocab_learn(LearnBody(words=[w["ar"] for w in words]), user, session)

    data = await vocab_stats(user, session)
    assert data["learned"] == 2
    assert sum(row["learned"] for row in data["levels"]) == 2


@pytest.mark.asyncio
async def test_daily_endpoint_skips_learned(session, make_user):
    from api.routes import LearnBody, vocab_daily, vocab_learn

    user = await make_user()
    first = (await vocab_daily("", 5, "", user, session))["items"]
    await vocab_learn(LearnBody(words=[w["ar"] for w in first]), user, session)
    second = (await vocab_daily("", 5, "", user, session))["items"]
    assert not ({w["id"] for w in first} & {w["id"] for w in second})
