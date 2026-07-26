"""Ma'lumotnoma — 156 darsdagi grammatika va lug'atni qidiriladigan ko'rinishda.

Kontent fayllardan bir marta yig'iladi (lru_cache) va butun kurs bo'ylab
qidiriladi: foydalanuvchi darsni qayta ochmasdan qoidani yoki so'zni topadi.
"""

import re
import unicodedata
from functools import lru_cache

from services.curriculum import load_curriculum, load_lesson_v2, written_lesson_ids

HARAKAT_RE = re.compile(r"[ً-ْٰ]")


def _strip_harakat(s: str) -> str:
    return HARAKAT_RE.sub("", s)


def normalize(s: str) -> str:
    """Qidiruv uchun: kichik harf, harakatsiz, alif/hamza birxil, apostrofsiz."""
    s = unicodedata.normalize("NFKC", s or "").lower().strip()
    s = _strip_harakat(s)
    s = re.sub(r"[أإآٱ]", "ا", s)
    s = re.sub(r"[ىي]", "ي", s)
    s = re.sub(r"[ةه]", "ه", s)
    s = re.sub(r"['`ʼ’‘ʻʿ]", "", s)
    return re.sub(r"\s+", " ", s)


@lru_cache(maxsize=1)
def grammar_entries() -> list[dict]:
    """Har darsdagi grammatika bo'limi — daraja va modul bo'yicha."""
    cur = load_curriculum()
    out: list[dict] = []
    for lid in sorted(written_lesson_ids()):
        meta = cur.get(lid)
        data = load_lesson_v2(lid)
        if not meta or not data:
            continue
        g = data.get("grammar") or {}
        if not (g.get("point_ar") or g.get("explanation_uz")):
            continue
        out.append(
            {
                "lesson_id": lid,
                "level": meta["level"],
                "module": meta.get("module", ""),
                "lesson_title": data.get("title_uz", ""),
                "point_ar": g.get("point_ar", ""),
                "explanation_uz": g.get("explanation_uz", ""),
                "table": g.get("table", []),
                "common_mistakes_uz": g.get("common_mistakes_uz", []),
            }
        )
    return out


@lru_cache(maxsize=1)
def vocab_entries() -> list[dict]:
    """Butun kursdagi lug'at — takrorlar birlashtirilgan."""
    cur = load_curriculum()
    seen: dict[str, dict] = {}
    for lid in sorted(written_lesson_ids()):
        meta = cur.get(lid)
        data = load_lesson_v2(lid)
        if not meta or not data:
            continue
        for v in data.get("vocabulary", []):
            key = normalize(v.get("ar", ""))
            if not key:
                continue
            if key in seen:
                seen[key]["lessons"].append(lid)
                continue
            seen[key] = {
                "ar": v.get("ar", ""),
                "translit": v.get("translit", ""),
                "uz": v.get("uz", ""),
                "root": v.get("root", ""),
                "pattern": v.get("pattern", ""),
                "pos": v.get("pos", ""),
                "audio": v.get("audio", ""),
                "example_ar": v.get("example_ar", ""),
                "example_uz": v.get("example_uz", ""),
                "level": meta["level"],
                "lessons": [lid],
            }
    return list(seen.values())


@lru_cache(maxsize=1)
def _vocab_index() -> list[tuple[str, int]]:
    """(qidiriladigan matn, indeks) — har so'rovda qayta qurilmasin."""
    return [
        (
            " ".join(
                normalize(x)
                for x in (
                    e["ar"], e["translit"], e["uz"], e["root"], e["pattern"]
                )
            ),
            i,
        )
        for i, e in enumerate(vocab_entries())
    ]


@lru_cache(maxsize=1)
def _grammar_index() -> list[tuple[str, int]]:
    return [
        (
            " ".join(
                normalize(x)
                for x in (
                    e["point_ar"], e["explanation_uz"], e["lesson_title"], e["module"]
                )
            ),
            i,
        )
        for i, e in enumerate(grammar_entries())
    ]


def search_vocab(
    query: str = "", level: str = "", limit: int = 60, offset: int = 0
) -> dict:
    entries = vocab_entries()
    q = normalize(query)
    idx = _vocab_index()

    hits = [i for text, i in idx if not q or q in text]
    if level:
        hits = [i for i in hits if entries[i]["level"] == level]

    # Qisqa so'z oldinroq — aniq moslik yuqoriga chiqadi
    if q:
        hits.sort(key=lambda i: (len(normalize(entries[i]["ar"])), entries[i]["level"]))

    return {
        "total": len(hits),
        "items": [entries[i] for i in hits[offset : offset + limit]],
    }


def search_grammar(query: str = "", level: str = "") -> dict:
    entries = grammar_entries()
    q = normalize(query)
    idx = _grammar_index()

    hits = [i for text, i in idx if not q or q in text]
    if level:
        hits = [i for i in hits if entries[i]["level"] == level]

    return {"total": len(hits), "items": [entries[i] for i in hits]}


def reference_stats() -> dict:
    return {
        "grammar_points": len(grammar_entries()),
        "vocab_words": len(vocab_entries()),
    }
