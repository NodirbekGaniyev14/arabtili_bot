"""Lug'at 2.0 sessiyasi (K24): daraja → mavzu → 10 so'z (2 × 5 fleshkarta) → 10 savollik test.

Oqim (klient, pages/vocab/VocabSession.tsx):
  1. Tanishtirish — har so'z: arabcha, tarjima, audio, kitobdan misol.
  2. Eslash — arabcha o'zi; «Javobni ko'rish» → «Bildim / Bilmadim»; bilmagani navbatga qaytadi.
  3. Test — 10 savol (arabcha→ma'no, eshitib→ma'no, ma'no→arabcha), 4 variant.
  4. Natija — foiz, xato so'zlar, XP; so'zlar SRS kartotekasiga (Takror bo'limi) tushadi.

«O'rganilgan» = so'z foydalanuvchining SRS kartotekasida (user_words) — darsdan kelgan bo'lsa ham.
Mavzuda yangi so'z qolmasa — «takrorlash» rejimi: eng zaif 10 so'z (xato ko'p, oson emas).
Baholash serverda: kalit + savol turi bo'yicha to'g'ri javob qayta hisoblanadi (klientga ishonilmaydi).
"""

import random
import re

from services import vocab

SESSION_WORDS = 10
BATCH = 5
OPTIONS = 4
KINDS = ("ar_uz", "audio_uz", "uz_ar")
PASS = 80  # foiz — bonus XP chegarasi
XP_BONUS = 5
REVIEW_BONUS = 3
DAILY_XP_CAP = 100  # lug'at sessiyalaridan kuniga ko'pi bilan (reyting adolatli qolsin)
XP_SOURCE = "vocab"

_ETYM = re.compile(r"\s*\((?:[^()]*o'zbekcha[^()]*)\)")
_PERSON_SUFFIX = re.compile(r"\s*·\s*u/erkak")


def split_uz(uz: str) -> tuple[str, str]:
    """(asosiy ma'no, eslatma): «kitob (o'zbekcha 'kitob' shundan)» → («kitob», «o'zbekcha 'kitob' shundan»).
    «ketdi, bordi · u/erkak» → «ketdi, bordi» (3-shaxs erkak — fe'l lug'at shakli, izohsiz ham tushunarli)."""
    uz = (uz or "").strip()
    hint = ""
    m = _ETYM.search(uz)
    if m:
        hint = m.group(0).strip()[1:-1].strip()
        uz = (uz[: m.start()] + uz[m.end():]).strip()
    uz = _PERSON_SUFFIX.sub("", uz)
    uz = re.sub(r"\(\s*\)", "", uz)
    uz = re.sub(r"\s+\)", ")", uz)
    uz = re.sub(r"\s{2,}", " ", uz).strip(" ·,")
    return uz, hint


def public(w: dict) -> dict:
    """Klientga — fleshkarta uchun kerakli maydonlar."""
    main, hint = split_uz(w.get("uz", ""))
    notes = [x for x in (hint, (w.get("note_uz") or "").strip()) if x]
    return {
        "key": w["key"],
        "ar": w["ar"],
        "translit": w.get("translit", ""),
        "uz": main,
        "audio": w.get("audio", ""),
        "example_ar": w.get("example_ar", ""),
        "example_uz": w.get("example_uz", ""),
        "note_uz": " · ".join(notes),
        "plural_ar": w.get("plural_ar", "") or "",
        "root": w.get("root", "") or "",
        "pos": w.get("pos", "") or "",
        "topic": w.get("topic", ""),
    }


# ─────────────────────────── ro'yxatlar ───────────────────────────


def _learned(pool, known: set[str]) -> int:
    return sum(1 for w in pool if w["key"] in known)


def levels(known: set[str]) -> dict:
    out = []
    for lv in vocab.LEVELS:
        pool = vocab.card_pool(lv)
        topics = [t for t in vocab.TOPICS if sum(1 for w in pool if w["topic"] == t["slug"]) >= vocab.MIN_TOPIC_WORDS]
        out.append(
            {
                "level": lv,
                **vocab.LEVEL_META[lv],
                "total": len(pool),
                "learned": _learned(pool, known),
                "topics": len(topics),
            }
        )
    return {
        "levels": out,
        "total": sum(x["total"] for x in out),
        "learned": sum(x["learned"] for x in out),
    }


def topics(level: str, known: set[str]) -> dict:
    pool = vocab.card_pool(level)
    items = []
    for t in vocab.TOPICS:
        words = [w for w in pool if w["topic"] == t["slug"]]
        if len(words) < vocab.MIN_TOPIC_WORDS:
            continue
        items.append(
            {
                "slug": t["slug"],
                "title_uz": t["title_uz"],
                "title_ar": t["title_ar"],
                "icon": t["icon"],
                "total": len(words),
                "learned": _learned(words, known),
            }
        )
    return {
        "level": level,
        **vocab.LEVEL_META[level],
        "total": len(pool),
        "learned": _learned(pool, known),
        "topics": items,
    }


def topic_meta(level: str, topic: str) -> dict:
    if topic == vocab.ALL_TOPIC:
        return {"slug": topic, "title_uz": f"Aralash — {level}", "title_ar": "مُخْتَلِط", "icon": "🎲"}
    t = vocab.TOPIC_BY_SLUG[topic]
    return {k: t[k] for k in ("slug", "title_uz", "title_ar", "icon")}


# ─────────────────────────── sessiya ───────────────────────────


def _answer(w: dict, kind: str) -> str:
    return w["ar"] if kind == "uz_ar" else split_uz(w["uz"])[0]


def _options(w: dict, kind: str, pool: list[dict], level_pool: tuple[dict, ...], rnd: random.Random) -> list[str]:
    """3 chalg'ituvchi: avval shu mavzudan (o'xshash so'zlar — haqiqiy bilim sinovi), yetmasa darajadan.
    Bir xil ko'rinadigan variant (ma'nosi aynan bir) chiqmaydi."""
    right = _answer(w, kind)
    picked: list[str] = []
    seen = {right, vocab.card_key(right) if kind == "uz_ar" else right.lower()}
    for source in (pool, level_pool):
        cands = [c for c in source if c["key"] != w["key"]]
        rnd.shuffle(cands)
        for c in cands:
            opt = _answer(c, kind)
            norm = vocab.card_key(opt) if kind == "uz_ar" else opt.lower()
            if not opt or norm in seen:
                continue
            seen.add(norm)
            picked.append(opt)
            if len(picked) == OPTIONS - 1:
                break
        if len(picked) == OPTIONS - 1:
            break
    options = picked + [right]
    rnd.shuffle(options)
    return options


def question(w: dict, kind: str, pool: list[dict], level: str, rnd: random.Random) -> dict:
    if kind == "audio_uz" and not w.get("audio"):
        kind = "ar_uz"
    return {
        "key": w["key"],
        "type": kind,
        "prompt": w["ar"] if kind != "uz_ar" else split_uz(w["uz"])[0],
        "audio": w.get("audio", "") if kind != "uz_ar" else "",
        "options": _options(w, kind, pool, vocab.card_pool(level), rnd),
        "answer": _answer(w, kind),
    }


def build(level: str, topic: str, known: dict[str, dict], n: int = SESSION_WORDS, seed: int | None = None) -> dict:
    """`known` — {card_key: {"lapses", "ease", "due"}} (foydalanuvchi kartotekasi).
    Yangi so'z bor — ular chastota tartibida; yo'q bo'lsa — eng zaif so'zlar takrori."""
    rnd = random.Random(seed)
    pool = vocab.topic_pool(level, topic)
    new = [w for w in pool if w["key"] not in known]
    if new:
        mode = "new"
        words = new[:n]
        remaining = len(new) - len(words)
    else:
        mode = "review"

        def weakness(w):
            k = known.get(w["key"], {})
            return (-(k.get("lapses") or 0), k.get("ease") or 2.5, k.get("due") or "9999")

        weakest = sorted(pool, key=weakness)[: max(n * 2, n)]
        words = rnd.sample(weakest, min(n, len(weakest)))
        remaining = 0
    order = words[:]
    rnd.shuffle(order)
    exam = [question(w, KINDS[i % len(KINDS)], pool, level, rnd) for i, w in enumerate(order)]
    return {
        "level": level,
        "topic": topic_meta(level, topic),
        "mode": mode,
        "batch": BATCH,
        "words": [public(w) for w in words],
        "exam": exam,
        "remaining": remaining,
        "total": len(pool),
        "learned": sum(1 for w in pool if w["key"] in known),
    }


def grade(level: str, answers: list[dict]) -> list[dict]:
    """Javoblarni tekshiradi (kalit bo'yicha so'z darajadan topiladi). Har kalit bir marta hisoblanadi.
    Qaytaradi: [{word, type, chosen, correct}] — noma'lum kalit/tur tashlab ketiladi."""
    by_key = {w["key"]: w for w in vocab.card_pool(level)}
    out: list[dict] = []
    seen: set[str] = set()
    for a in answers[: SESSION_WORDS + 2]:
        key, kind = a.get("key", ""), a.get("type", "")
        w = by_key.get(key)
        if not w or key in seen or kind not in KINDS:
            continue
        seen.add(key)
        chosen = (a.get("chosen") or "").strip()
        out.append({"word": w, "type": kind, "chosen": chosen, "correct": chosen == _answer(w, kind)})
    return out


def xp_for(correct: int, total: int, mode: str) -> int:
    if not total:
        return 0
    pct = round(correct / total * 100)
    if mode == "review":
        return correct // 2 + (REVIEW_BONUS if pct >= PASS else 0)
    return correct + (XP_BONUS if pct >= PASS else 0)
