"""Javobsiz test (K33): daraja imtihoni, mini-imtihon va haftalik chellenj — ballni SERVER hisoblaydi.

Mijozga savollar to'g'ri javobsiz beriladi (`public_item`), mijoz faqat o'quvchining javobini yuboradi
(variantli savolda — tanlangan matn, yozma savolda — terilgan matn, harakat/tartib — yig'ilgan so'z),
`check_item` baholaydi. Javob o'quvchiga baholangach — natija ekranidagi `review` da ko'rsatiladi.

Savol turi bo'yicha qoidalar webapp/src/pages/v2/exercises.tsx `renderExercise` ning nusxasi; yozma javob
qoidalari — services/answer_check.py (answerCheck.ts nusxasi, tests/test_answer_check_parity.py solishtiradi).
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

from services.answer_check import (
    ar_ok,
    blank_fills,
    harakat_ok,
    is_arabic,
    lat_ok,
    norm_ar,
    split_harakat,
)

# Klaviatura talab qiladigan turlar ba'zan TAYYOR VARIANTLAR bilan yoziladi — bunda variantli test (exercises.tsx)
KEYBOARD_TYPES = {"fill_blank", "harakat", "dictation", "translate_uz_ar"}

# match_root: variantlar poolda bo'lmasa — o'zak + 3 ta chalg'ituvchi o'zak (exercises.tsx FALLBACK_ROOTS)
FALLBACK_ROOTS = ["ك ت ب", "د ر س", "ع ل م", "س ف ر", "ن ظ ر", "ق ب ل", "ح ك م"]
# build_word: to'liq harakatli qoliplar (exerciseLogic.ts FALLBACK_PATTERNS)
FALLBACK_PATTERNS = [
    "فَاعِل", "مَفْعُول", "مَفْعَل", "فِعَال", "تَفْعِيل", "مُفَعِّل", "مُفَاعِل", "اِسْتِفْعَال", "فَعِيل", "فُعُول",
]

INPUT_KINDS = ("options", "ar", "lat", "harakat", "order")


def apply_pattern(pattern: str, root: str) -> str:
    letters = [x for x in re.split(r"[\s\-]+", root or "") if x]
    if len(letters) < 3:
        return pattern
    sub = {"ف": letters[0], "ع": letters[1], "ل": letters[2]}
    return "".join(sub.get(ch, ch) for ch in pattern)


def build_word_distractors(root: str, answer: str) -> list[str]:
    """3 ta chalg'ituvchi: javob bilan (yoki bir-biri bilan) HARAKATSIZ yozilishi bir xil so'z olinmaydi (#F150)."""
    seen = {norm_ar(answer)}
    out: list[str] = []
    for p in FALLBACK_PATTERNS:
        w = apply_pattern(p, root)
        k = norm_ar(w)
        if k in seen:
            continue
        seen.add(k)
        out.append(w)
        if len(out) == 3:
            break
    return out


def input_kind(item: dict) -> str:
    """Savol qanday javob qabul qiladi: variant tanlash / arabcha yozish / lotincha yozish / harakat / so'z tartibi."""
    t = item.get("type")
    opts = item.get("options") or []
    if t in KEYBOARD_TYPES and len(opts) >= 2:
        return "options"
    if t in ("mcq", "match_root", "build_word"):
        return "options"
    if t == "translate_uz_ar" or t == "dictation":
        return "ar"
    if t == "translate_ar_uz":
        return "lat"
    if t == "fill_blank":
        return "ar" if is_arabic(item.get("answer", "")) else "lat"
    if t == "harakat":
        return "harakat"
    if t == "order_words":
        return "order"
    return ""


def supported(item: dict) -> bool:
    return bool(input_kind(item)) and bool(str(item.get("answer", "")).strip())


def _options_for(item: dict, rnd: random.Random) -> list[str]:
    answer = item["answer"]
    options = list(dict.fromkeys(item.get("options") or []))
    if not options:
        if item.get("type") == "match_root":
            pool = [r for r in FALLBACK_ROOTS if r not in (item.get("root"), answer)]
            options = [answer, *rnd.sample(pool, min(3, len(pool)))]
        elif item.get("type") == "build_word":
            options = [answer, *build_word_distractors(item.get("root", ""), answer)]
    if answer not in options:
        options.append(answer)  # kontentda javob variantlar orasida bo'lmasa ham savol yechilsin
    rnd.shuffle(options)
    return options


def public_item(item: dict, rnd: random.Random | None = None) -> dict:
    """Mijozga beriladigan savol: to'g'ri javob, izoh va `accept` YO'Q."""
    rnd = rnd or random.Random()
    kind = input_kind(item)
    out: dict = {
        "type": item.get("type", ""),
        "q_uz": item.get("q_uz") or "",
        "q_ar": item.get("q_ar") or "",
        "audio": item.get("audio") or "",
        "input": kind,
        "options": [],
    }
    if kind == "options":
        out["options"] = _options_for(item, rnd)
    elif kind == "harakat":
        out["base"] = "".join(base for base, _ in split_harakat(item["answer"]))
    elif kind == "order":
        words = list(item.get("words") or []) or str(item["answer"]).split()
        rnd.shuffle(words)
        out["words"] = words
    if item.get("type") == "build_word":
        # «o'zak + vazn» — savolning o'zi (javob ulardan yasaladi)
        out["root"] = item.get("root", "")
        out["pattern"] = item.get("pattern", "")
    return out


def public_items(items: list[dict], rnd: random.Random | None = None) -> list[dict]:
    rnd = rnd or random.Random()
    return [public_item(i, rnd) for i in items]


def _blank_src(item: dict) -> str:
    if item.get("q_ar"):
        return item["q_ar"]
    m = re.search(r"«([^»]*_{2,}[^»]*)»", item.get("q_uz") or "")
    return m.group(1) if m else ""


def check_item(item: dict, given: str) -> bool:
    """Bitta savol: o'quvchi javobi to'g'rimi (renderExercise bilan bir xil qoidalar)."""
    given = (given or "").strip()
    if not given:
        return False
    kind = input_kind(item)
    ans = item["answer"]
    accept = list(item.get("accept") or [])
    prompt = item.get("q_uz") or ""
    t = item.get("type")
    if kind == "options":
        return given == ans
    if t == "translate_uz_ar":
        return ar_ok(ans, given, accept=accept, mode="translate", prompt=prompt)
    if t == "translate_ar_uz":
        return lat_ok(ans, given, accept=accept, prompt=prompt)
    if t == "fill_blank":
        if is_arabic(ans):
            return ar_ok(ans, given, accept=accept + blank_fills(_blank_src(item), ans), mode="fill", prompt=prompt)
        return lat_ok(ans, given, accept=accept, prompt=prompt)
    if t == "dictation":
        return ar_ok(ans, given, accept=accept, mode="strict")
    if t == "harakat":
        return harakat_ok(ans, given)
    if t == "order_words":
        return norm_ar(given) == norm_ar(ans)
    return False


def _wrong_word(item: dict) -> str:
    """Xato so'z takrorga (SRS) qaytadi: arabcha javob, bo'lmasa arabcha savol (QuizRunner bilan bir xil)."""
    if is_arabic(item.get("answer", "")):
        return item["answer"]
    return item["q_ar"] if is_arabic(item.get("q_ar", "")) else ""


@dataclass
class GradeResult:
    correct: int
    total: int
    #: xato javoblar — natija ekranida «To'g'ri javob» bilan (javob qulflangach ko'rsatiladi)
    review: list[dict] = field(default_factory=list)
    wrong_words: list[str] = field(default_factory=list)
    #: (savol, javob) — rad etilgan YOZMA javoblar (admin /javoblar jurnaliga)
    rejected: list[tuple[dict, str]] = field(default_factory=list)


def grade_items(items: list[dict], answers: list[str] | None) -> GradeResult:
    given = list(answers or [])
    correct = 0
    res = GradeResult(correct=0, total=len(items))
    for i, item in enumerate(items):
        g = given[i] if i < len(given) else ""
        if check_item(item, g):
            correct += 1
            continue
        res.review.append(
            {
                "index": i,
                "type": item.get("type", ""),
                "q_uz": item.get("q_uz") or "",
                "q_ar": item.get("q_ar") or "",
                "options": list(item.get("options") or []),
                "audio": item.get("audio") or "",
                "answer": item["answer"],
                "explain_uz": item.get("explain_uz") or "",
                "given": (g or "")[:300],
            }
        )
        w = _wrong_word(item)
        if w:
            res.wrong_words.append(w)
        if input_kind(item) in ("ar", "lat", "harakat") and (g or "").strip():
            res.rejected.append((item, g))
    res.correct = correct
    return res
