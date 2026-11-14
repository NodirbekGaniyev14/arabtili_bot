"""K33 — javobsiz test (services/blind_quiz.py): savol ko'rinishi, har tur baholanishi, natija va xatolar ro'yxati."""

import glob
import json
import random
from pathlib import Path

import pytest

from services import blind_quiz as bq
from services.checkpoint import ALLOWED_TYPES

ROOT = Path(__file__).resolve().parent.parent
SECRET = {"answer", "explain_uz", "option_notes", "accept"}


def _bank() -> list[dict]:
    out = []
    for f in sorted(glob.glob(str(ROOT / "content/modules/*/*.json"))):
        for t in json.load(open(f, encoding="utf-8")).get("micro_test", []):
            if t.get("type") in ALLOWED_TYPES and str(t.get("answer", "")).strip():
                out.append(t)
    return out


# ── Kontent butunligi: mini-imtihon va chellenjga tushishi mumkin bo'lgan HAR savol baholanadi ──


def test_every_bank_item_is_gradable_and_hides_the_answer():
    bank = _bank()
    assert len(bank) > 1000
    rnd = random.Random(1)
    for it in bank:
        assert bq.supported(it), f"baholab bo'lmaydigan savol: {it['type']} {it['answer']}"
        pub = bq.public_item(it, rnd)
        assert not SECRET & set(pub), pub
        if it["type"] != "build_word":
            assert "root" not in pub and "pattern" not in pub, pub
        if pub["input"] == "options":
            assert it["answer"] in pub["options"], "variantli savolda to'g'ri javob bo'lishi shart"
            assert len(set(pub["options"])) == len(pub["options"])
            assert len(pub["options"]) >= 2, it
        else:
            assert pub["options"] == []
        # o'zining to'g'ri javobi har doim qabul qilinadi
        assert bq.check_item(it, it["answer"]), (it["type"], it["answer"])
        for a in it.get("accept") or []:
            if pub["input"] in ("ar", "lat"):
                assert bq.check_item(it, a), (it["type"], a)


def test_harakat_base_has_letters_only():
    it = {"type": "harakat", "q_uz": "q", "answer": "مُدَرِّسٌ"}
    pub = bq.public_item(it)
    assert pub["input"] == "harakat" and pub["base"] == "مدرس"


def test_order_words_are_shuffled_copy_of_words():
    it = {"type": "order_words", "q_uz": "q", "answer": "هُوَ طَبِيبٌ", "words": ["هُوَ", "طَبِيبٌ", "جَدِيدٌ"]}
    pub = bq.public_item(it, random.Random(3))
    assert sorted(pub["words"]) == sorted(it["words"]) and pub["input"] == "order"


def test_options_are_shuffled_not_answer_first():
    bank = [i for i in _bank() if i["type"] == "mcq"][:200]
    rnd = random.Random(9)
    firsts = sum(bq.public_item(i, rnd)["options"][0] == i["answer"] for i in bank)
    assert firsts < len(bank) * 0.5, "to'g'ri javob doim birinchi emasligi kerak (poolda shunday edi)"


def test_match_root_and_build_word_options_are_server_built():
    mr = {"type": "match_root", "q_uz": "o'zak", "q_ar": "مَكْتَب", "answer": "ك ت ب", "root": "ك ت ب"}
    pub = bq.public_item(mr)
    assert len(pub["options"]) == 4 and "ك ت ب" in pub["options"]
    bw = {"type": "build_word", "q_uz": "yasang", "root": "ك ت ب", "pattern": "مَفْعُول", "answer": "مَكْتُوب"}
    pub = bq.public_item(bw)
    assert pub["root"] == "ك ت ب" and pub["pattern"] == "مَفْعُول", "o'zak va vazn — savolning o'zi"
    assert len(pub["options"]) == 4 and "مَكْتُوب" in pub["options"]


def test_answer_missing_from_options_is_repaired():
    it = {"type": "mcq", "q_uz": "q", "options": ["a", "b"], "answer": "c"}
    assert "c" in bq.public_item(it)["options"]


def test_options_item_with_options_uses_them_even_for_match_root():
    it = {"type": "match_root", "q_uz": "Qaysi so'z «ط ل ب» o'zagidan?", "options": ["طَالِب", "طَبِيب", "مُدَرِّس"],
          "answer": "طَالِب", "root": "ط ل ب"}
    assert sorted(bq.public_item(it)["options"]) == sorted(it["options"])


# ── Baholash: har tur ──


def test_options_exact_only():
    it = {"type": "mcq", "options": ["a", "b", "c"], "answer": "a"}
    assert bq.check_item(it, "a") and bq.check_item(it, " a ")
    assert not bq.check_item(it, "b") and not bq.check_item(it, "") and not bq.check_item(it, "A")


def test_translate_ar_uz_is_lenient_like_the_client():
    it = {"type": "translate_ar_uz", "q_ar": "كَتَبْتِ", "answer": "sen (ayol) yozding", "q_uz": ""}
    assert bq.check_item(it, "sen yozding")
    assert bq.check_item(it, "Сен ёздинг")
    assert not bq.check_item(it, "men yozdim")
    assert not bq.check_item(it, "")


def test_translate_uz_ar_ignores_harakat_hamza_and_article():
    it = {"type": "translate_uz_ar", "q_uz": "kitob", "answer": "الكِتَاب"}
    assert bq.check_item(it, "كتاب") and bq.check_item(it, "الكتاب")
    assert not bq.check_item(it, "قلم")


def test_translate_uz_ar_strict_when_question_is_about_article():
    it = {"type": "translate_uz_ar", "q_uz": "artikl bilan: kitob", "answer": "الكِتَاب"}
    assert bq.check_item(it, "الكتاب") and not bq.check_item(it, "كتاب")


def test_fill_blank_arabic_accepts_full_word_for_attached_blank():
    it = {"type": "fill_blank", "q_ar": "عَلَّمَ___", "q_uz": "Bo'sh joy", "answer": "هُمْ"}
    assert bq.check_item(it, "هم") and bq.check_item(it, "علمهم")
    assert not bq.check_item(it, "كتابهم")


def test_fill_blank_latin_answer_uses_latin_check():
    it = {"type": "fill_blank", "q_uz": "bo'sh joy", "answer": "bir qalam"}
    assert bq.check_item(it, "qalam") and not bq.check_item(it, "kitob")
    assert bq.input_kind(it) == "lat"


def test_dictation_strict_but_forgives_ya_and_ta_marbuta():
    it = {"type": "dictation", "answer": "مَتى"}
    assert bq.check_item(it, "متي") and not bq.check_item(it, "ما")


def test_harakat_case_ending_is_optional():
    it = {"type": "harakat", "q_uz": "q", "answer": "مُدَرِّس"}
    assert bq.check_item(it, "مُدَرِّس")
    assert bq.check_item(it, "مُدَرِّسُ")  # e'rob harakati — to'g'ri
    assert not bq.check_item(it, "مَدَرِّس")
    assert not bq.check_item(it, "مدرس"), "harakatsiz — javob emas"


def test_order_words_ignores_harakat():
    it = {"type": "order_words", "answer": "هُوَ طَبِيبٌ", "words": ["طَبِيبٌ", "هُوَ"]}
    assert bq.check_item(it, "هو طبيب") and not bq.check_item(it, "طبيب هو")


def test_unknown_type_is_never_correct():
    it = {"type": "shadowing", "answer": "x"}
    assert not bq.supported(it) and not bq.check_item(it, "x")


# ── Natija ──


def test_grade_items_review_wrong_words_and_rejected():
    items = [
        {"type": "mcq", "q_uz": "q1", "options": ["a", "b"], "answer": "a", "explain_uz": "izoh"},
        {"type": "mcq", "q_uz": "q2", "q_ar": "كِتَاب", "options": ["x", "y"], "answer": "x"},
        {"type": "translate_uz_ar", "q_uz": "kitob", "answer": "كِتَاب"},
        {"type": "translate_ar_uz", "q_ar": "قَلَم", "answer": "qalam"},
        {"type": "translate_ar_uz", "q_ar": "بَيْت", "answer": "uy"},
    ]
    g = bq.grade_items(items, ["a", "y", "كتاب", "daftar"])  # oxirgisi — javobsiz
    assert (g.correct, g.total) == (2, 5)
    assert [r["index"] for r in g.review] == [1, 3, 4]
    assert g.review[0]["answer"] == "x" and g.review[0]["given"] == "y"
    assert g.review[2]["given"] == ""
    # xato so'zlar: arabcha javob yo'q — arabcha savol
    assert g.wrong_words == ["كِتَاب", "قَلَم", "بَيْت"]
    # rad etilgan YOZMA javoblar — faqat bo'sh bo'lmaganlari (variantli xato bu yerga tushmaydi)
    assert [(i["q_ar"], given) for i, given in g.rejected] == [("قَلَم", "daftar")]


def test_grade_items_extra_answers_ignored_and_none_is_all_wrong():
    items = [{"type": "mcq", "options": ["a", "b"], "answer": "a"}] * 2
    assert bq.grade_items(items, ["a", "a", "a", "a"]).correct == 2
    assert bq.grade_items(items, None).correct == 0
    assert bq.grade_items([], []).total == 0
