"""Lug'at imtihoni — daraja kesimida (K16.6).

Savollar lug'at bazasining O'ZIDAN yig'iladi: dars kerak emas, foydalanuvchi
istalgan darajaning so'zlarini sinab ko'radi. Uch tur:
  ar_uz    — arabcha so'z beriladi, o'zbekcha ma'nosi tanlanadi
  uz_ar    — o'zbekcha ma'no beriladi, arabcha so'z tanlanadi
  audio_uz — talaffuz eshittiriladi, ma'nosi tanlanadi

Chalg'ituvchi variantlar imkon qadar SHU darajadan va SHU mavzudan olinadi —
shunda tanlov haqiqiy bilimni tekshiradi, taxminni emas.
"""

import random

from services.vocab import LEVELS, all_words

PASS_SCORE = 70  # foiz — lug'at imtihonidan o'tish chegarasi
DEFAULT_COUNT = 20
MAX_COUNT = 40
OPTIONS = 4


def _pool(level: str = "", theme: str = "") -> list[dict]:
    """Imtihonga yaroqli so'zlar: ma'nosi va (audio turi uchun) talaffuzi bor."""
    out = []
    for w in all_words():
        if level and w["level"] != level:
            continue
        if theme and w.get("theme") != theme:
            continue
        if w["ar"] and w["uz"]:
            out.append(w)
    return out


def _distractors(word: dict, pool: list[dict], key: str, rnd: random.Random) -> list[str]:
    """3 ta chalg'ituvchi: avval shu mavzudan, yetmasa darajadan."""
    right = word[key]
    same_theme = [
        w[key] for w in pool
        if w["id"] != word["id"] and w.get("theme") and w.get("theme") == word.get("theme")
    ]
    rest = [w[key] for w in pool if w["id"] != word["id"]]

    picked: list[str] = []
    for source in (same_theme, rest):
        rnd.shuffle(source)
        for candidate in source:
            if candidate and candidate != right and candidate not in picked:
                picked.append(candidate)
            if len(picked) == OPTIONS - 1:
                return picked
    return picked


def _question(word: dict, pool: list[dict], kind: str, rnd: random.Random) -> dict | None:
    if kind == "audio_uz" and not word.get("audio"):
        kind = "ar_uz"

    if kind == "uz_ar":
        answer, key, prompt = word["ar"], "ar", word["uz"]
    else:  # ar_uz va audio_uz — javob o'zbekcha
        answer, key, prompt = word["uz"], "uz", word["ar"]

    others = _distractors(word, pool, key, rnd)
    if len(others) < OPTIONS - 1:
        return None

    options = others + [answer]
    rnd.shuffle(options)
    return {
        "type": kind,
        "word_id": word["id"],
        "ar": word["ar"],
        "prompt": prompt,
        "translit": word["translit"],
        "audio": word.get("audio", "") if kind == "audio_uz" else "",
        "options": options,
        "answer": answer,
        "level": word["level"],
        "theme": word.get("theme", ""),
    }


def build_quiz(
    level: str = "",
    theme: str = "",
    n: int = DEFAULT_COUNT,
    seed: int | None = None,
) -> dict:
    """Daraja (va ixtiyoriy mavzu) bo'yicha imtihon yig'adi."""
    pool = _pool(level, theme)
    n = max(5, min(n, MAX_COUNT))
    rnd = random.Random(seed)

    if len(pool) < OPTIONS:
        return {"level": level, "theme": theme, "pass_score": PASS_SCORE, "items": []}

    chosen = rnd.sample(pool, min(n, len(pool)))
    kinds = ["ar_uz", "uz_ar", "audio_uz"]
    items = []
    for i, word in enumerate(chosen):
        q = _question(word, pool, kinds[i % len(kinds)], rnd)
        if q:
            items.append(q)

    return {
        "level": level,
        "theme": theme,
        "pass_score": PASS_SCORE,
        "total_words": len(pool),
        "items": items,
    }


def score(correct: int, total: int) -> dict:
    pct = round(correct / total * 100) if total else 0
    return {"score": pct, "passed": pct >= PASS_SCORE, "pass_score": PASS_SCORE}


def levels_ready(minimum: int = OPTIONS) -> list[str]:
    """Imtihon uchun yetarli so'zi bor darajalar."""
    return [lv for lv in LEVELS if len(_pool(lv)) >= minimum]
