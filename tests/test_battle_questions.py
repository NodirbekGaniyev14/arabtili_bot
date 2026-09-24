"""K25.5 — Oktagon savollari qiyinroq: o'xshash chalg'ituvchilar (turkum, o'zak, vazn, yozilish),
sinonim variant yo'q, javobni sezdiruvchi izohlar olib tashlangan, o'zlashma so'zlar «ma'no → arabcha»."""

import random
import time
from functools import lru_cache

import pytest

from services import battle as bt
from services import battle_questions as bq
from services import vocab
from services import vocab_session as vs


# ── ma'no tozalash ──


@pytest.mark.parametrize(
    "uz,want",
    [
        ("hurmatli (murojaatda — 'muhtaram'!)", "hurmatli"),
        ("yo'q (Saudi «yo'q/bo'lmaydi»)", "yo'q"),
        ("ayt! (amr, ajvaf) · buyruq (sen)", "ayt!"),
        ("o'qish, tahsil (masdar)", "o'qish, tahsil"),
        ("sindi (o'zi) (VII bob · u — lug'at shakli)", "sindi (o'zi)"),
        ("tingladi (diqqat bilan) (VIII bob)", "tingladi (diqqat bilan)"),
        ("kitob (o'zbekcha 'kitob' shundan)", "kitob"),
        ("yodgorlik, iz (ko'pligi: آثار — 'asar')", "yodgorlik, iz"),
        # Mazmunni aniqlovchi izohlar QOLADI
        ("u (erkak)", "u (erkak)"),
        ("u (ayol)", "u (ayol)"),
        ("bu (erkak so'zga)", "bu (erkak so'zga)"),
        ("och (rang)", "och (rang)"),
    ],
)
def test_meaning_cleanup(uz, want):
    assert bq.meaning({"uz": uz}) == want


def test_senses_detect_synonyms():
    assert bq.senses("ish, amal") & bq.senses("amal, harakat") == {"amal"}
    assert not (bq.senses("u (erkak)") & bq.senses("u (ayol)")), "u (erkak) ≠ u (ayol) — juftlik qoladi"
    assert bq.senses("qildi, bajardi") & bq.senses("ishladi; qildi")


def test_loanword_leak():
    assert bq.leaks({"translit": "kitaab", "uz": "kitob"})
    assert bq.leaks({"translit": "ʿamal", "uz": "ish, amal"})
    assert bq.leaks({"translit": "waqt", "uz": "vaqt"})
    assert not bq.leaks({"translit": "kataba", "uz": "yozdi"})
    assert not bq.leaks({"translit": "hal", "uz": "-mi (ha/yo'q savoli)"})


# ── savollar ──


@lru_cache(maxsize=16)
def _shown_map(level: str, kind: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for f in bq._index(level)[0].values():
        out.setdefault(f["ar"] if kind == "uz_ar" else f["meaning"], f)
    return out


def _feature(level: str, shown: str, kind: str) -> dict | None:
    return _shown_map(level, kind).get(shown)


@pytest.mark.parametrize("level", vocab.LEVELS)
def test_questions_are_fair(level):
    """Har savol: 4 xil variant, javob ichida, sinonim yo'q, ma'noda arabcha yo'q; o'zlashma — uz_ar."""
    rnd = random.Random(f"fair-{level}")
    by_key = bq._index(level)[0]
    pool = [w for w in vocab.card_pool(level) if by_key[w["key"]]["ok"]]
    for w in rnd.sample(pool, min(80, len(pool))):
        for kind in bq.KINDS:
            q = bq.question(w, kind, level, rnd)
            t = by_key[w["key"]]
            assert len(q["options"]) == 4 and len(set(q["options"])) == 4 and q["answer"] in q["options"]
            if t["leak"]:
                assert q["type"] == "uz_ar", f"o'zlashma so'z tovushidan topilmasin: {w['ar']} / {t['meaning']}"
            for o in q["options"]:
                if o == q["answer"]:
                    continue
                c = _feature(level, o, q["type"])
                assert c is not None and not (c["senses"] & t["senses"]), (w["ar"], q["answer"], o)
            if q["type"] == "ar_uz":
                assert not bq._ARABIC.search(" ".join(q["options"]))


@pytest.mark.parametrize("level", ["A1", "A2", "B1"])
def test_distractors_harder_than_topic_random(level):
    """Yangi chalg'ituvchilar eski usuldagidan (mavzudan tasodifiy) ancha o'xshashroq va asosan shu turkumdan."""
    rnd = random.Random(f"hard-{level}")
    by_key = bq._index(level)[0]
    pool = [w for w in vocab.card_pool(level) if by_key[w["key"]]["ok"]]
    new_sim = old_sim = 0.0
    same_pos = total = 0
    for w in rnd.sample(pool, 60):
        t = by_key[w["key"]]
        kind = "uz_ar"
        new = bq.question(w, kind, level, rnd)
        topic_pool = vocab.topic_pool(level, w["topic"]) if w.get("topic") else list(vocab.card_pool(level))
        old = vs.question(w, kind, topic_pool, level, rnd)
        for q, acc in ((new, "new"), (old, "old")):
            for o in q["options"]:
                if o == q["answer"]:
                    continue
                c = _feature(level, o, kind)
                if c is None:
                    continue
                s = bq.similarity(t, c, kind)
                if acc == "new":
                    new_sim += s
                    total += 1
                    same_pos += c["pos"] == t["pos"]
                else:
                    old_sim += s
    assert new_sim > old_sim * 1.3, (new_sim, old_sim)  # A1: ~1.36×, A2/B1: >1.5×
    assert same_pos / total > 0.9, same_pos / total


def test_same_root_distractors_appear():
    """كِتَاب kabi so'zga o'zakdosh variantlar (كَاتِب, مَكْتَب…) tez-tez chiqadi."""
    level = "A0"
    by_key = bq._index(level)[0]
    kitab = next(w for w in vocab.card_pool(level) if w["key"] == vocab.card_key("كِتَاب"))
    root = by_key[kitab["key"]]["root"]
    hits = 0
    for seed in range(30):
        q = bq.question(kitab, "uz_ar", level, random.Random(seed))
        hits += any(
            (c := _feature(level, o, "uz_ar")) is not None and c["root"] == root and o != q["answer"] for o in q["options"]
        )
    assert hits >= 15, hits  # ~60% savolda o'zakdosh variant (qolganida — vazni/yozilishi o'xshash)


def test_battle_build_uses_hard_questions_fast():
    for lv in vocab.LEVELS:
        bq._index(lv)  # indeks keshi (server hayoti davomida bir marta)
    t0 = time.perf_counter()
    qs = bt.build_questions("B2", random.Random(5))
    assert (time.perf_counter() - t0) < 0.5, "jang boshlanishini sekinlashtirmasin"
    assert len(qs) == bt.QUESTIONS and {q["type"] for q in qs} <= set(bq.KINDS)
    assert all(q["audio"] == "" for q in qs)


def test_arabic_meaning_words_excluded():
    """Ma'nosida arabcha qolgan grammatik yozuvlar jangga tushmaydi (na savol, na variant)."""
    for lv in vocab.LEVELS:
        by_key, by_pos, everyone = bq._index(lv)
        assert all(f["ok"] for f in everyone)
        assert all(f["ok"] for group in by_pos.values() for f in group)
        bad = {k for k, f in by_key.items() if not f["ok"]}
        for seed in range(5):
            assert not ({q["key"] for q in bq.build(lv, random.Random(seed), 10)} & bad)
