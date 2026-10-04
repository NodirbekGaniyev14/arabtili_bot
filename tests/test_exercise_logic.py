"""K29.4 — mashq mantig'i (webapp/src/pages/v2/exerciseLogic.ts) node orqali.

#F158 / a0-28 «mudarris»: o'quvchi oxirgi harfga e'rob harakati qo'ysa «to'g'ri javobim xato hisoblandi» (4 kishi);
#F150 / a2-20 «so'z yasash»: variantlardan biri javobning harakatsiz nusxasi (مَكْتُوب ↔ مَكْتوب) edi;
#F151: fo'il/maf'ul variantlari (مُعَلِّم ↔ مُعَلَّم) faqat bitta harakat bilan farq qiladi — eslatma ko'rsatiladi.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
RUNNER = ROOT / "tests" / "js" / "answer_check_runner.cjs"
ESBUILD = ROOT / "webapp" / "node_modules" / "esbuild"

pytestmark = pytest.mark.skipif(
    not shutil.which("node") or not ESBUILD.exists(), reason="node yoki webapp/node_modules yo'q"
)

MIM, DAL, RA, SIN = "م", "د", "ر", "س"
FATHA, DAMMA, KASRA, SHADDA, SUKUN = "َ", "ُ", "ِ", "ّ", "ْ"
TANWIN_DAMMA = "ٌ"

# Kontentdagi javob: ر ustida kasra + shadda (birinchi kasra)
ANSWER = MIM + DAMMA + DAL + FATHA + RA + KASRA + SHADDA + SIN
# O'quvchi ekran klaviaturasida avval shadda, keyin kasra qo'yadi — belgilar tartibi teskari, lekin bir xil harakat
TYPED = MIM + DAMMA + DAL + FATHA + RA + SHADDA + KASRA + SIN


def run(cases: list[list]) -> list:
    r = subprocess.run(
        ["node", str(RUNNER), "exerciseLogic.ts"],
        input=json.dumps(cases),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def verdict(user: str, answer: str = ANSWER) -> dict:
    return run([["harakatCheck", user, answer]])[0]


def test_harakat_exact_regardless_of_mark_order():
    v = verdict(TYPED)
    assert v["ok"] and v["exact"] and v["wrong"] == []


@pytest.mark.parametrize("ending", [DAMMA, FATHA, KASRA, TANWIN_DAMMA])
def test_case_ending_on_bare_final_letter_is_accepted(ending):
    """#F158: namunada oxirgi harf yalang'och; e'rob harakati qo'ygan o'quvchi to'g'ri."""
    v = verdict(TYPED + ending)
    assert v["ok"] and v["exact"] is False
    assert "Oxirgi harf" in v["note"] and v["wrong"] == [3]


@pytest.mark.parametrize(
    "user",
    [
        MIM + FATHA + DAL + FATHA + RA + SHADDA + KASRA + SIN,  # مَدَرِّس — boshidagi harakat boshqa
        MIM + DAMMA + DAL + FATHA + RA + KASRA + SIN,  # shadda tushgan
        MIM + DAMMA + DAL + FATHA + RA + SHADDA + FATHA + SIN,  # kasra o'rniga fatha
        TYPED + SHADDA,  # oxirgi harfga shadda — e'rob emas
        MIM + DAMMA + DAL + FATHA + RA + KASRA + SIN + DAMMA,  # shadda tushgan + oxirgi harakat
        MIM + FATHA + DAL + FATHA + RA + SHADDA + KASRA + SIN + DAMMA,  # xato + oxirgi harakat
    ],
)
def test_real_mistakes_still_rejected(user):
    assert verdict(user)["ok"] is False


def test_old_end_rules_unchanged():
    # Namunada oxirgi e'rob bor, o'quvchi qo'ymagan — avvalgidek kechiriladi
    ans = MIM + DAMMA + DAL + FATHA + RA + KASRA + SHADDA + SIN + DAMMA
    v = verdict(TYPED, ans)
    assert v["ok"] and v["exact"] is False and "E'rob" in v["note"]
    # Faqat sukun farqi
    v = verdict(MIM + DAMMA + DAL + FATHA + RA + KASRA + SHADDA + SIN, MIM + SUKUN + DAMMA + DAL + FATHA + RA + KASRA + SHADDA + SIN)
    assert v["ok"] and "Sukun" in v["note"]


def test_apply_mark_builds_same_marks_as_answer():
    # shadda → kasra va kasra → shadda ikkalasi ham ر ustida {shadda, kasra}
    a, b = run([["applyMark", SHADDA, KASRA], ["applyMark", KASRA, SHADDA]])
    assert sorted(a) == sorted(b) == sorted(KASRA + SHADDA)


# ── so'z yasash distraktorlari ──


_HARAKAT = re.compile("[ً-ٰٟـ]")


def _bare(s: str) -> str:
    return _HARAKAT.sub("", s)


def _build_word_items() -> list[dict]:
    items: list[dict] = []

    def walk(o):
        if isinstance(o, dict):
            if o.get("type") == "build_word" and o.get("root") and o.get("answer"):
                items.append(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    for f in sorted((ROOT / "content").rglob("*.json")):
        try:
            walk(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            continue
    return items


def test_build_word_options_never_contain_lookalikes():
    """Barcha kontentdagi «so'z yasash»: javob + 3 distraktor — hammasi harakatsiz yozilishida ham har xil."""
    items = _build_word_items()
    assert len(items) >= 15
    res = run([["buildWordDistractors", {"root": it["root"], "answer": it["answer"]}] for it in items])
    for it, dist in zip(items, res):
        assert len(dist) == 3, it["answer"]
        bares = [_bare(x) for x in [it["answer"], *dist]]
        assert len(set(bares)) == 4, (it["answer"], dist)


def test_f150_case():
    (dist,) = run([["buildWordDistractors", {"root": "ك ت ب", "answer": "مَكْتُوب"}]])
    assert "مَكْتوب" not in dist and "مَكْتُوب" not in dist


def test_lookalike_detection():
    fail, maful, other = "مُعَلِّم", "مُعَلَّم", "كَتَبَ"
    a, b, c = run([
        ["hasLookalikes", [fail, maful, other]],
        ["hasLookalikes", ["كَاتِب", "كِتَاب", "مَكْتَب"]],
        ["hasLookalikes", ["ـتـ", "تـ", "ـت"]],  # harf shakllari — harakat emas
    ])
    assert a is True and b is False and c is False
