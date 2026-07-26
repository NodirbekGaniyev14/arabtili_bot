"""Mini-imtihonlar (checkpoint) — har darajaning 25% / 50% / 75% nuqtasida.

Yakuniy daraja imtihonidan (services/exam.py) farqi:
- savollar ALOHIDA bank emas, o'sha darajada O'TILGAN darslarning micro_test
  savollaridan yig'iladi (kümülativ) — shuning uchun har doim mavzuga mos;
- faqat avtomatik baholanadigan turlar (yozish/gapirish yo'q);
- yiqilsa QULF YO'Q va kutish muddati yo'q — natija ko'rsatiladi, zaif so'zlar
  takrorga tushadi.
"""

import random

from services.curriculum import lesson_order, load_curriculum, load_lesson_v2

PASS = 80  # o'tish chegarasi (%)
N_QUESTIONS = 12
PERCENTS = (25, 50, 75)

# Mini-imtihonda ishlatiladigan turlar (o'zi baholanadi, matn kiritish minimal)
ALLOWED_TYPES = {
    "mcq",
    "translate_ar_uz",
    "translate_uz_ar",
    "fill_blank",
    "match_root",
    "build_word",
    "harakat",
    "order_words",
}


def level_lessons(level: str) -> list[str]:
    """Shu darajaning YOZILGAN dars ID'lari — kurikulum tartibida."""
    from services.curriculum import written_lesson_ids

    cur = load_curriculum()
    written = written_lesson_ids()
    return [
        lid
        for lid in lesson_order()
        if cur[lid]["level"] == level
        and cur[lid]["type"] == "lesson"
        and lid in written
    ]


def checkpoints_for(level: str) -> list[dict]:
    """[{percent, need, upto}] — need: tugatilishi kerak bo'lgan dars soni,
    upto: imtihonga kiradigan darslar soni (kümülativ, need bilan bir xil)."""
    total = len(level_lessons(level))
    if total < 4:  # juda kichik daraja — mini-imtihon ma'nosiz
        return []
    out = []
    for p in PERCENTS:
        need = max(1, round(total * p / 100))
        if need >= total:  # 100% ga tegib ketmasin — u yakuniy imtihon
            continue
        out.append({"percent": p, "need": need, "upto": need})
    return out


def _vocab_mcq(lessons: list[str], rnd: random.Random) -> list[dict]:
    """Lug'atdan 4 variantli test savollari yasaydi (o'zbekcha → arabcha)."""
    pool: list[tuple[str, str]] = []  # (ar, uz)
    for lid in lessons:
        data = load_lesson_v2(lid) or {}
        for v in data.get("vocabulary", []):
            ar, uz = v.get("ar", "").strip(), v.get("uz", "").strip()
            if ar and uz:
                pool.append((ar, uz))
    if len(pool) < 4:
        return []

    items = []
    for ar, uz in pool:
        others = [a for a, _ in pool if a != ar]
        if len(others) < 3:
            continue
        options = rnd.sample(others, 3) + [ar]
        rnd.shuffle(options)
        items.append(
            {
                "type": "mcq",
                "q_uz": f"«{uz}» — qaysi so'z?",
                "q_ar": "",
                "options": options,
                "answer": ar,
                "explain_uz": f"{ar} — {uz}",
                "audio": "",
                "root": "",
                "pattern": "",
                "words": [],
            }
        )
    return items


def question_bank(lessons: list[str]) -> list[dict]:
    """Darslarning micro_test savollari (yaroqli turlar)."""
    bank = []
    for lid in lessons:
        data = load_lesson_v2(lid) or {}
        for t in data.get("micro_test", []):
            if t.get("type") not in ALLOWED_TYPES:
                continue
            if not str(t.get("answer", "")).strip():
                continue
            bank.append(dict(t))
    return bank


def build_mini(level: str, percent: int, seed: int | None = None) -> dict | None:
    """Checkpoint uchun imtihon yig'adi: N_QUESTIONS ta savol."""
    cps = {c["percent"]: c for c in checkpoints_for(level)}
    cp = cps.get(percent)
    if not cp:
        return None

    lessons = level_lessons(level)[: cp["upto"]]
    rnd = random.Random(seed)

    bank = question_bank(lessons)
    rnd.shuffle(bank)
    items = bank[:N_QUESTIONS]

    # Yetmasa — lug'atdan yasalgan test savollari bilan to'ldiramiz
    if len(items) < N_QUESTIONS:
        extra = _vocab_mcq(lessons, rnd)
        rnd.shuffle(extra)
        seen = {i.get("answer") for i in items}
        for it in extra:
            if len(items) >= N_QUESTIONS:
                break
            if it["answer"] in seen:
                continue
            items.append(it)
            seen.add(it["answer"])

    if not items:
        return None

    # mcq variantlarini aralashtiramiz (dars tartibi yodda qolmasin)
    for it in items:
        if it.get("type") == "mcq" and it.get("options"):
            opts = list(it["options"])
            rnd.shuffle(opts)
            it["options"] = opts

    rnd.shuffle(items)
    return {
        "level": level,
        "percent": percent,
        "lessons_covered": len(lessons),
        "items": items,
        "pass_score": PASS,
    }


def grade(correct: int, total: int) -> dict:
    score = round(100 * correct / total) if total else 0
    return {"score": score, "passed": score >= PASS, "correct": correct, "total": total}
