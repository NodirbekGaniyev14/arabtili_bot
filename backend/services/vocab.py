"""Lug'at bazasi — darajalar kesimida 6000 so'z (K16, docs/VOCAB_PLAN.md).

Ikki manba birlashtiriladi:
  1. `content/vocab/{level}.json` — mustaqil lug'at (qo'lda yoziladi)
  2. darslardagi lug'at (`services/reference.vocab_entries`)

Bitta so'z ikki marta chiqmaydi: solishtiruv harakatsiz-normallashtirilgan
shaklda (`reference.normalize`) ketadi, dars yozuvi ustun turadi va lug'at
bazasidagi qo'shimcha maydonlar (mavzu, vazn, ko'plik) unga qo'shib qo'yiladi.
"""

import json
import re
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

# ── K24 Lug'at 2.0: daraja → mavzu → 5 talik fleshkarta → test ──

# Daraja nomlari — kurs bilan bir xil (services/course._level_name, sertifikat)
LEVEL_META: dict[str, dict] = {
    "A0": {"title_uz": "Boshlang'ich", "title_ar": "التَّأْسِيس"},
    "A1": {"title_uz": "Elementar", "title_ar": "المُبْتَدِئ"},
    "A2": {"title_uz": "O'rta-quyi", "title_ar": "مَا قَبْلَ المُتَوَسِّط"},
    "B1": {"title_uz": "O'rta", "title_ar": "المُتَوَسِّط"},
    "B2": {"title_uz": "O'rta-yuqori", "title_ar": "فَوْقَ المُتَوَسِّط"},
}

# O'quvchiga ko'rinadigan mavzular: 36 ta ichki mavzu (THEMES) 17 guruhga jamlanadi —
# har darajada bir xil tartib, kichik mavzular bo'sh qolmaydi.
TOPICS: list[dict] = [
    {"slug": "muomala", "title_uz": "Salomlashish va muomala", "title_ar": "التَّحِيَّةُ وَالتَّعَامُلُ", "icon": "👋", "themes": ["salomlashuv", "munosabat"]},
    {"slug": "oila", "title_uz": "Oila va inson", "title_ar": "الأُسْرَةُ وَالإِنْسَانُ", "icon": "👨‍👩‍👧", "themes": ["oila", "xarakter", "his-tuygu"]},
    {"slug": "uy", "title_uz": "Uy va kiyim", "title_ar": "البَيْتُ وَاللِّبَاسُ", "icon": "🏠", "themes": ["uy", "kiyim"]},
    {"slug": "ovqat", "title_uz": "Ovqat va restoran", "title_ar": "الطَّعَامُ وَالمَطْعَمُ", "icon": "🍽", "themes": ["ovqat", "restoran"]},
    {"slug": "salomatlik", "title_uz": "Tana va salomatlik", "title_ar": "الجِسْمُ وَالصِّحَّةُ", "icon": "🩺", "themes": ["salomatlik"]},
    {"slug": "vaqt", "title_uz": "Vaqt, son va rang", "title_ar": "الوَقْتُ وَالأَعْدَادُ", "icon": "🕐", "themes": ["vaqt", "son-olchov", "rang-shakl"]},
    {"slug": "safar", "title_uz": "Shahar va safar", "title_ar": "المَدِينَةُ وَالسَّفَرُ", "icon": "✈️", "themes": ["shahar-transport", "safar", "mehmonxona"]},
    {"slug": "bozor", "title_uz": "Bozor, pul va iqtisod", "title_ar": "السُّوقُ وَالمَالُ", "icon": "💰", "themes": ["xarid", "pul-bank", "iqtisod"]},
    {"slug": "talim", "title_uz": "Ta'lim va fikr", "title_ar": "التَّعْلِيمُ وَالفِكْرُ", "icon": "🎓", "themes": ["maktab", "tafakkur"]},
    {"slug": "ish", "title_uz": "Ish va kasblar", "title_ar": "العَمَلُ وَالمِهَنُ", "icon": "💼", "themes": ["kasblar", "ish"]},
    {"slug": "tabiat", "title_uz": "Tabiat va ob-havo", "title_ar": "الطَّبِيعَةُ وَالطَّقْسُ", "icon": "🌿", "themes": ["hayvon", "osimlik", "ob-havo", "geografiya", "ekologiya"]},
    {"slug": "madaniyat", "title_uz": "Madaniyat, din va sport", "title_ar": "الثَّقَافَةُ وَالدِّينُ", "icon": "🕌", "themes": ["marosim"]},
    {"slug": "davlat", "title_uz": "Davlat va hujjatlar", "title_ar": "الدَّوْلَةُ وَالقَانُونُ", "icon": "🏛", "themes": ["davlat-qonun", "hujjat"]},
    {"slug": "texnologiya", "title_uz": "Texnologiya va OAV", "title_ar": "التِّقْنِيَةُ وَالإِعْلَامُ", "icon": "💻", "themes": ["texnologiya", "yangiliklar"]},
    {"slug": "fellar", "title_uz": "Fe'llar", "title_ar": "الأَفْعَالُ", "icon": "🏃", "themes": ["fellar"]},
    {"slug": "sifatlar", "title_uz": "Sifatlar", "title_ar": "الصِّفَاتُ", "icon": "✨", "themes": ["sifatlar"]},
    {"slug": "yordamchi", "title_uz": "Yordamchi so'zlar", "title_ar": "الأَدَوَاتُ", "icon": "🔗", "themes": ["boglovchi"]},
]
TOPIC_BY_SLUG = {t["slug"]: t for t in TOPICS}
THEME_TOPIC = {th: t["slug"] for t in TOPICS for th in t["themes"]}
ALL_TOPIC = "all"  # «Aralash» — butun daraja
MIN_TOPIC_WORDS = 4  # bundan kam so'zli mavzu ro'yxatda ko'rinmaydi (so'zlari «Aralash»da)

LESSON_THEMES_PATH = VOCAB_DIR / "lesson_themes.json"

# Fleshkartaga yaramaydigan dars shakllari (grammatika mashqlari uchun tuslangan/ulangan shakllar)
_PERSON = re.compile(r"^\(?(men|sen|biz|siz|sizlar|ular|u \(ayol\)|\(ayol\))\b", re.I)
_POSSESSIVE = re.compile(r"^(mening|sening|uning|bizning|sizning|sizlarning|ularning)\b", re.I)


@lru_cache(maxsize=1)
def lesson_themes() -> tuple[dict[str, str], frozenset[str]]:
    """content/vocab/lesson_themes.json: dars so'ziga mavzu (kalit — normalize(ar)) va istisnolar."""
    if not LESSON_THEMES_PATH.exists():
        return {}, frozenset()
    data = json.loads(LESSON_THEMES_PATH.read_text(encoding="utf-8"))
    return dict(data.get("themes", {})), frozenset(data.get("exclude", []))


def card_ok(w: dict) -> bool:
    """So'z fleshkarta sifatida o'rgatishga yaroqlimi: harf/skelet, tuslangan fe'l («men yozdim»),
    egalik («mening kitobim»), ikkilik, idofa namunasi, ko'plik ko'rsatkichi — yo'q."""
    uz = (w.get("uz") or "").strip()
    pos = w.get("pos") or ""
    if not w.get("ar") or not uz:
        return False
    if normalize(w["ar"]) in lesson_themes()[1]:
        return False
    if pos == "harf" or "skelet" in uz or "birikma" in uz:
        return False
    if pos == "fe'l" and (_PERSON.search(uz) or "(kelasi" in uz or "(ikkilik)" in uz or uz.startswith("u ikki ")):
        return False
    if _POSSESSIVE.search(uz):
        return False
    if "(idafa)" in uz or "sifatida:" in uz or " holati (" in uz or "ko'pligi)" in uz:
        return False
    if pos in ("ot", "ism", "noun") and re.search(r"\((erkak|ayol)\)", uz):
        return False
    if pos in ("ot", "ism", "noun") and uz.startswith("ikki ") and re.search(r"(انِ|انْ|ينِ)$", w["ar"]):
        return False
    if pos == "sifat" and ("(ayol)" in uz or "muannas" in uz):
        return False
    return True


_HARAKAT = re.compile(r"[\u064B-\u0652\u0670\u0640]")


def card_key(ar: str) -> str:
    """Takrorni aniqlash kaliti: normalize + aniqlik artikli «ال» olib tashlanadi
    (بَيْت = الْبَيْت). «أَلَم» kabi hamzali boshlanish tegilmaydi — faqat harakatsiz shakli
    oddiy «ال» bilan boshlansa."""
    key = normalize(ar)
    bare = _HARAKAT.sub("", ar or "").strip()
    if bare.startswith("ال") and len(key) > 4 and key.startswith("ال"):
        key = key[2:]
    return key


def topic_of(w: dict) -> str:
    return THEME_TOPIC.get(w.get("theme") or "", "")


@lru_cache(maxsize=8)
def card_pool(level: str) -> tuple[dict, ...]:
    """Darajaning fleshkartaga yaroqli so'zlari, chastota tartibida, «ال»siz takrorlarsiz.
    Har so'zda `topic` (TOPICS slug) va `key` (card_key) bor."""
    seen: set[str] = set()
    out = []
    for w in all_words():
        if w["level"] != level or not card_ok(w):
            continue
        key = card_key(w["ar"])
        if not key or key in seen:
            continue
        seen.add(key)
        out.append({**w, "key": key, "topic": topic_of(w)})
    if level in ("A0", "A1"):
        # Boshlang'ichda darslardagi eng oddiy so'zlar (ona, uy, kitob…) oldin — keyin chastota bo'yicha
        out.sort(key=lambda w: w.get("source") != "lesson")
    return tuple(out)


def topic_pool(level: str, topic: str) -> list[dict]:
    pool = card_pool(level)
    if topic == ALL_TOPIC:
        return list(pool)
    return [w for w in pool if w["topic"] == topic]


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

    lesson_theme = lesson_themes()[0]
    for i, e in enumerate(vocab_entries()):
        key = normalize(e["ar"])
        if not key or key in by_key:
            continue
        w = _from_lesson(e, i)
        w["theme"] = lesson_theme.get(key, "")  # K24: dars so'zlari ham mavzuga tushadi
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
                # root/pattern majburiy emas: ibora va o'zlashma so'zlarda yo'q
                for x in (
                    w["ar"],
                    w["translit"],
                    w["uz"],
                    w.get("root") or "",
                    w.get("pattern") or "",
                )
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
