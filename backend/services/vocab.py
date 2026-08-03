"""Lug'at bazasi — darajalar kesimida 6000 so'z (K16, docs/VOCAB_PLAN.md).

Ikki manba birlashtiriladi:
  1. `content/vocab/{level}.json` — mustaqil lug'at (qo'lda yoziladi)
  2. darslardagi lug'at (`services/reference.vocab_entries`)

Bitta so'z ikki marta chiqmaydi: solishtiruv harakatsiz-normallashtirilgan
shaklda (`reference.normalize`) ketadi, dars yozuvi ustun turadi va lug'at
bazasidagi qo'shimcha maydonlar (mavzu, vazn, ko'plik) unga qo'shib qo'yiladi.
"""

import json
from functools import lru_cache

from config import BASE_DIR
from services.reference import normalize, vocab_entries

VOCAB_DIR = BASE_DIR / "content" / "vocab"

LEVELS = ("A0", "A1", "A2", "B1", "B2")

# Daraja bo'yicha maqsad (docs/ARABIY_CURRICULUM.md §2.5 — jamlangan 6000)
TARGETS = {"A0": 150, "A1": 650, "A2": 1200, "B1": 1800, "B2": 2200}

# So'z turkumlari — darslardagi atamalar bilan bir xil (eng ko'p ishlatilgani «ot»)
POS = (
    "ot",
    "fe'l",
    "sifat",
    "ravish",
    "son",
    "olmosh",
    "predlog",
    "yuklama",
    "bog'lovchi",
    "ibora",
)

# Mavzular — 36 ta (docs/VOCAB_PLAN.md §2)
THEMES: dict[str, str] = {
    # Kundalik
    "oila": "Oila",
    "uy": "Uy va jihoz",
    "ovqat": "Ovqat va ichimlik",
    "kiyim": "Kiyim",
    "salomatlik": "Tana va salomatlik",
    "vaqt": "Vaqt va sana",
    "ob-havo": "Ob-havo",
    "rang-shakl": "Rang va shakl",
    "son-olchov": "Son va o'lchov",
    # Harakat
    "shahar-transport": "Shahar va transport",
    "safar": "Safar va aeroport",
    "mehmonxona": "Mehmonxona",
    "xarid": "Xarid va bozor",
    "pul-bank": "Pul va bank",
    "restoran": "Restoran",
    # Ijtimoiy
    "salomlashuv": "Salomlashuv va odob",
    "his-tuygu": "His-tuyg'u",
    "xarakter": "Xarakter",
    "munosabat": "Munosabat va do'stlik",
    "marosim": "Marosim va bayram",
    # Ta'lim va ish
    "maktab": "Maktab va universitet",
    "kasblar": "Kasblar",
    "ish": "Ofis va ish",
    "texnologiya": "Texnologiya va internet",
    "hujjat": "Hujjat va rasmiyat",
    # Jamiyat
    "davlat-qonun": "Davlat va qonun",
    "yangiliklar": "Yangiliklar va siyosat",
    "iqtisod": "Iqtisod va savdo",
    # Tabiat
    "hayvon": "Hayvonlar",
    "osimlik": "O'simliklar",
    "geografiya": "Geografiya",
    "ekologiya": "Ekologiya",
    # Til yadrosi
    "fellar": "Harakat fe'llari",
    "sifatlar": "Sifatlar",
    "boglovchi": "Bog'lovchi va yuklama",
    "tafakkur": "Fikr va tafakkur",
}

# Lug'at bazasidan olinadigan, dars yozuvida bo'lmasligi mumkin qo'shimcha maydonlar
EXTRA_FIELDS = ("theme", "plural_ar", "note_uz", "past_ar", "present_ar", "masdar_ar", "form")


def _empty(level: str) -> dict:
    return {"level": level, "words": []}


@lru_cache(maxsize=8)
def load_level(level: str) -> list[dict]:
    """Bitta darajaning lug'at fayli. Fayl yo'q bo'lsa — bo'sh ro'yxat."""
    path = VOCAB_DIR / f"{level.lower()}.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("words", [])


def _from_lesson(e: dict, order: int) -> dict:
    """Dars lug'ati yozuvini lug'at sxemasiga keltiradi."""
    return {
        "id": f"l-{order:05d}",
        "rank": 0,  # darsdagi so'zda chastota reytingi yo'q
        "ar": e["ar"],
        "translit": e.get("translit", ""),
        "uz": e.get("uz", ""),
        "pos": e.get("pos", ""),
        "root": e.get("root", ""),
        "pattern": e.get("pattern", ""),
        "theme": "",
        "level": e["level"],
        "example_ar": e.get("example_ar", ""),
        "example_uz": e.get("example_uz", ""),
        "audio": e.get("audio", ""),
        "note_uz": "",
        "lessons": e.get("lessons", []),
        "source": "lesson",
    }


@lru_cache(maxsize=1)
def all_words() -> list[dict]:
    """Butun lug'at: dars so'zlari + mustaqil baza, takrorlarsiz."""
    by_key: dict[str, dict] = {}
    out: list[dict] = []

    for i, e in enumerate(vocab_entries()):
        key = normalize(e["ar"])
        if not key or key in by_key:
            continue
        w = _from_lesson(e, i)
        by_key[key] = w
        out.append(w)

    for level in LEVELS:
        for w in load_level(level):
            key = normalize(w.get("ar", ""))
            if not key:
                continue
            old = by_key.get(key)
            if old is not None:
                # Dars yozuvi ustun — faqat yetishmagan maydonlarni to'ldiramiz
                for f in EXTRA_FIELDS:
                    if w.get(f) and not old.get(f):
                        old[f] = w[f]
                if w.get("rank") and not old.get("rank"):
                    old["rank"] = w["rank"]
                continue
            entry = {**w, "lessons": [], "source": "vocab"}
            entry.setdefault("note_uz", "")
            by_key[key] = entry
            out.append(entry)

    # Chastota tartibi: reytingi borlar oldin, keyin daraja va so'z uzunligi
    out.sort(
        key=lambda w: (
            LEVELS.index(w["level"]) if w["level"] in LEVELS else len(LEVELS),
            w["rank"] or 10**6,
            len(normalize(w["ar"])),
        )
    )
    return out


@lru_cache(maxsize=1)
def _index() -> list[tuple[str, int]]:
    """(qidiriladigan matn, indeks) — har so'rovda qayta qurilmasin."""
    return [
        (
            " ".join(
                normalize(x)
                for x in (w["ar"], w["translit"], w["uz"], w["root"], w["pattern"])
            ),
            i,
        )
        for i, w in enumerate(all_words())
    ]


def search(
    q: str = "",
    level: str = "",
    theme: str = "",
    pos: str = "",
    limit: int = 60,
    offset: int = 0,
) -> dict:
    words = all_words()
    needle = normalize(q)

    hits = [i for text, i in _index() if not needle or needle in text]
    if level:
        hits = [i for i in hits if words[i]["level"] == level]
    if theme:
        hits = [i for i in hits if words[i].get("theme") == theme]
    if pos:
        hits = [i for i in hits if words[i].get("pos") == pos]

    if needle:  # aniq moslik yuqoriga
        hits.sort(key=lambda i: (len(normalize(words[i]["ar"])), words[i]["level"]))

    return {
        "total": len(hits),
        "items": [words[i] for i in hits[offset : offset + limit]],
    }


def theme_list(level: str = "") -> list[dict]:
    """Mavzular va ulardagi so'z soni (bo'sh mavzular ham ko'rinadi)."""
    counts: dict[str, int] = {slug: 0 for slug in THEMES}
    for w in all_words():
        t = w.get("theme")
        if t in counts and (not level or w["level"] == level):
            counts[t] += 1
    return [
        {"slug": slug, "title_uz": title, "total": counts[slug]}
        for slug, title in THEMES.items()
    ]


def level_counts() -> dict[str, int]:
    counts = {lv: 0 for lv in LEVELS}
    for w in all_words():
        if w["level"] in counts:
            counts[w["level"]] += 1
    return counts


def stats() -> dict:
    counts = level_counts()
    return {
        "total": sum(counts.values()),
        "goal": sum(TARGETS.values()),
        "levels": [
            {
                "level": lv,
                "total": counts[lv],
                "target": TARGETS[lv],
            }
            for lv in LEVELS
        ],
    }


def daily_set(known: set[str], level: str = "", n: int = 20) -> list[dict]:
    """Kunlik to'plam — o'rganilmagan so'zlardan, chastota tartibida."""
    known_keys = {normalize(a) for a in known}
    out = []
    for w in all_words():
        if level and w["level"] != level:
            continue
        if normalize(w["ar"]) in known_keys:
            continue
        out.append(w)
        if len(out) >= n:
            break
    return out


def word_by_ar(ar: str) -> dict | None:
    key = normalize(ar)
    for w in all_words():
        if normalize(w["ar"]) == key:
            return w
    return None
