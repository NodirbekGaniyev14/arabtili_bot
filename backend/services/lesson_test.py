"""Dars mikro-testi — har urinishda BOSHQA savollar (K14).

Nega kerak: 60% dan past natija endi darsni tugatilgan hisoblamaydi
(`api/v2.complete_v2`), ya'ni o'quvchi qayta topshiradi. Agar savollar aynan
o'sha bo'lsa, ikkinchi urinishda javoblar yodlab olinadi va qulf ma'nosini
yo'qotadi.

Bank ikki qismdan yig'iladi:
  1) darsda YOZILGAN `micro_test` savollari (eng sifatlisi — birinchi navbatda);
  2) dars mazmunidan yasalgan savollar: lug'at (o'zbekcha→arabcha,
     arabcha→o'zbekcha, tinglash), grammatika jadvali, o'zak yasalmalari.

Urinish raqami bank ichida "oyna" tanlaydi: 1-urinish birinchi N savol,
2-urinish keyingi N va h.k. Tartib dars ID'si bo'yicha barqaror
aralashtiriladi, shuning uchun ketma-ket urinishlar KESISHMAYDI (bank
2N dan katta bo'lsa).
"""

import random
import re
from functools import lru_cache

from services.curriculum import load_curriculum, load_lesson_v2, written_lesson_ids
from services.qbank import qhash, shuffle_options

PASS_SCORE = 60  # spec §11 — darsdan o'tish chegarasi (%)
MIN_QUESTIONS = 6
MAX_QUESTIONS = 10

# Mikro-testda ishlatiladigan turlar (avtomatik baholanadi)
ALLOWED_TYPES = {
    "mcq",
    "translate_ar_uz",
    "translate_uz_ar",
    "fill_blank",
    "match_root",
    "build_word",
    "harakat",
    "order_words",
    "dictation",
    "shadowing",
}

FALLBACK_ROOTS = ["ك ت ب", "د ر س", "ع ل م", "س ف ر", "ن ظ ر", "ق ب ل", "ح ك م"]


def _mcq(
    q_uz: str,
    answer: str,
    distractors: list[str],
    *,
    q_ar: str = "",
    audio: str = "",
    explain: str = "",
    notes: dict[str, str] | None = None,
) -> dict | None:
    """4 variantli savol (variantlar noyob bo'lishi shart).
    `notes` — K28: xato variant tanlansa ko'rsatiladigan izoh (u aslida qaysi so'z: «u (ayol) yozdi» = كَتَبَتْ)."""
    options = [answer]
    for d in distractors:
        if d and d not in options:
            options.append(d)
        if len(options) == 4:
            break
    if len(options) < 3:
        return None
    item = {
        "type": "mcq",
        "q_uz": q_uz,
        "q_ar": q_ar,
        "options": options,
        "answer": answer,
        "explain_uz": explain,
        "audio": audio,
        "root": "",
        "pattern": "",
        "words": [],
    }
    opt_notes = {o: notes[o] for o in options[1:] if notes and notes.get(o)}
    if opt_notes:
        item["option_notes"] = opt_notes
    return item


_HARAKAT = re.compile("[" + chr(0x064B) + "-" + chr(0x065F) + chr(0x0670) + chr(0x0640) + "]")


def _bare(s: str) -> str:
    return " ".join(_HARAKAT.sub("", s or "").split())


def same_word(a: str, b: str) -> bool:
    """Bir so'z: aynan bir xil yoki biri harakatsiz yozilgan (ب / بَ, مدرسة / مَدْرَسَة).
    Ikkalasida harakat bo'lsa farq muhim (كَتَبْتُ ≠ كَتَبَتْ) — bu atayin qo'yilgan distraktor."""
    a, b = a.strip(), b.strip()
    if a == b:
        return True
    return _bare(a) == _bare(b) and (not _HARAKAT.search(a) or not _HARAKAT.search(b))


@lru_cache(maxsize=8)
def _level_vocab(level: str) -> tuple[tuple[str, str], ...]:
    """Darajadagi barcha (arabcha, o'zbekcha) juftlar — distraktorlar uchun."""
    cur = load_curriculum()
    written = written_lesson_ids()
    pairs: list[tuple[str, str]] = []
    for lid, meta in cur.items():
        if meta["level"] != level or meta["type"] != "lesson" or lid not in written:
            continue
        data = load_lesson_v2(lid) or {}
        for v in data.get("vocabulary", []):
            ar, uz = str(v.get("ar", "")).strip(), str(v.get("uz", "")).strip()
            if ar and uz:
                pairs.append((ar, uz))
    return tuple(dict.fromkeys(pairs))  # takrorlarini olib tashlaymiz


def generated_bank(lesson_id: str) -> list[dict]:
    """Dars mazmunidan yasalgan qo'shimcha savollar."""
    data = load_lesson_v2(lesson_id)
    if not data:
        return []
    level = data.get("level") or load_curriculum().get(lesson_id, {}).get("level", "A0")

    vocab = [
        v
        for v in data.get("vocabulary", [])
        if str(v.get("ar", "")).strip() and str(v.get("uz", "")).strip()
    ]
    pool = list(_level_vocab(level)) or [(v["ar"], v["uz"]) for v in vocab]
    ars = [a for a, _ in pool]
    uzs = [u for _, u in pool]

    # K28: barcha juftlar (lug'at + jadval + yasalmalar) — IKKINCHI TO'G'RI JAVOBni distraktordan chiqarish uchun.
    # Audit: 31 savolda ikkinchi to'g'ri variant bor edi (تَكْتُبُ: «u (ayol) yozadi» ham «sen yozasan» ham;
    # A0 harf tavsiflari ikki xil matnda; بُنِيَ, إِعْرَاب …) — «to'g'ri javobim xato hisoblandi».
    table = (data.get("grammar") or {}).get("table") or []
    derived = [d for r in data.get("roots", []) for d in r.get("derived", [])]
    pairs = list(pool) + [(v["ar"].strip(), v["uz"].strip()) for v in vocab]
    pairs += [(str(x.get("ar", "")).strip(), str(x.get("uz", "")).strip()) for x in table + derived]
    pairs = [(a, u) for a, u in pairs if a and u]
    uz_note = {}  # o'zbekcha variant → u qaysi arabcha so'z
    ar_note = {}  # arabcha variant → ma'nosi
    for a, u in pairs:
        uz_note.setdefault(u, a)
        ar_note.setdefault(a, u)

    def meanings(ar: str) -> set[str]:
        return {u for a, u in pairs if same_word(a, ar)}

    def uz_distractors(ar: str, extra: list[str] = ()) -> list[str]:
        bad = meanings(ar)
        return [u for u in [*extra, *uzs] if u not in bad]

    def ar_distractors(ar: str, uz: str) -> list[str]:
        syn = {a for a, u in pairs if u == uz}
        return [a for a in ars if not same_word(a, ar) and a not in syn]

    out: list[dict] = []

    for v in vocab:
        ar, uz = v["ar"].strip(), v["uz"].strip()
        other_ar = ar_distractors(ar, uz)

        # o'zbekcha → arabcha
        q = _mcq(f"«{uz}» — qaysi so'z?", ar, other_ar, explain=f"{ar} — {uz}", notes=ar_note)
        if q:
            out.append(q)
        # arabcha → o'zbekcha (arabcha katta ko'rinadi)
        q = _mcq(
            "Bu so'z nima degani?",
            uz,
            uz_distractors(ar),
            q_ar=ar,
            audio=v.get("audio", ""),
            explain=f"{ar} — {uz}",
            notes=uz_note,
        )
        if q:
            out.append(q)
        # tinglash (audio bor bo'lsa)
        if v.get("audio"):
            q = _mcq(
                "Eshiting va so'zni toping",
                ar,
                other_ar,
                audio=v["audio"],
                explain=f"{ar} — {uz}",
                notes=ar_note,
            )
            if q:
                out.append(q)
        # o'zak (dars o'zaklaridan)
        if v.get("root"):
            roots = [
                r["root"] for r in data.get("roots", []) if r.get("root") != v["root"]
            ] + [r for r in FALLBACK_ROOTS if r != v["root"]]
            q = _mcq(
                "Bu so'z qaysi o'zakdan?",
                v["root"],
                roots,
                q_ar=ar,
                explain=f"{ar} — o'zak: {v['root']}",
            )
            if q:
                out.append(q)

    # Grammatika jadvali: arabcha shakl → o'zbekcha ma'no
    for row in table:
        ar, uz = str(row.get("ar", "")).strip(), str(row.get("uz", "")).strip()
        if not ar or not uz:
            continue
        others = [str(r.get("uz", "")).strip() for r in table if str(r.get("uz", "")).strip() != uz]
        q = _mcq("Tarjimasi qaysi?", uz, uz_distractors(ar, others), q_ar=ar, notes=uz_note)
        if q:
            out.append(q)

    # O'zak yasalmalari
    for r in data.get("roots", []):
        for d in r.get("derived", []):
            ar, uz = str(d.get("ar", "")).strip(), str(d.get("uz", "")).strip()
            if not ar or not uz:
                continue
            q = _mcq(
                "Bu yasalma nima degani?",
                uz,
                uz_distractors(ar, [str(x.get("uz", "")).strip() for x in r.get("derived", [])]),
                q_ar=ar,
                explain=f"{r.get('root', '')} o'zagidan",
                notes=uz_note,
            )
            if q:
                out.append(q)

    return out


def authored_bank(lesson_id: str) -> list[dict]:
    data = load_lesson_v2(lesson_id) or {}
    return [
        dict(t)
        for t in data.get("micro_test", [])
        if t.get("type") in ALLOWED_TYPES and str(t.get("answer", "")).strip()
    ]


def full_bank(lesson_id: str) -> list[dict]:
    """Darsning butun savol banki: yozilganlar OLDINDA, keyin yasalganlar.

    Tartib barqaror (dars ID'si urug' bo'ladi), shuning uchun urinishlar
    bo'lingan bo'laklar har doim bir xil bo'lib qoladi.
    """
    generated = generated_bank(lesson_id)
    random.Random(lesson_id).shuffle(generated)

    bank: list[dict] = []
    seen: set[str] = set()
    for it in authored_bank(lesson_id) + generated:
        h = qhash(it)
        if h in seen:
            continue
        seen.add(h)
        bank.append(it)
    return bank


def build_test(lesson_id: str, attempt: int = 0) -> dict:
    """Urinish raqamiga mos mikro-test.

    Bank teng bo'laklarga bo'linadi: 1-urinish 1-bo'lak (dars muallifi yozgan
    savollar), 2-urinish 2-bo'lak va h.k. Bo'laklar KESISHMAYDI, shuning uchun
    yiqilgan o'quvchiga aynan o'sha savollar tushmaydi. Bo'laklar tugasa
    aylanadi (bank chekli).
    """
    bank = full_bank(lesson_id)
    if not bank:
        return {"items": [], "attempt": attempt, "pass_score": PASS_SCORE}

    authored_n = len(authored_bank(lesson_id))
    n = max(MIN_QUESTIONS, min(MAX_QUESTIONS, authored_n or MIN_QUESTIONS))
    n = min(n, len(bank))

    chunks = max(1, len(bank) // n)  # faqat to'liq bo'laklar
    idx = max(0, attempt) % chunks
    items = bank[idx * n : idx * n + n]

    rnd = random.Random(f"{lesson_id}:{attempt}")
    rnd.shuffle(items)
    return {
        "items": shuffle_options(items, rnd),
        "attempt": max(0, attempt),
        "pass_score": PASS_SCORE,
        "variants": chunks,
    }
