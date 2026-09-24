"""Oktagon savollari (K25.5) — qiyinroq variantlar.

Muammo (o'quvchilar fikri): variantlar juda oson edi — chalg'ituvchilar mavzudan tasodifiy olinardi,
ko'pincha boshqa so'z turkumi, boshqa uzunlik, boshqa ko'rinish; javobni bilmasdan ham topsa bo'lardi.

Endi har chalg'ituvchi to'g'ri javobga O'XSHASHLIGI bo'yicha tanlanadi:
  - bir xil so'z turkumi (fe'l ↔ fe'l, ot ↔ ot) — asosiy filtr;
  - bir xil o'zak (كِتَاب ↔ كَاتِب ↔ مَكْتَب) va bir xil vazn (مُرَاقَبَة ↔ مُرَاجَعَة);
  - yozilishi o'xshash (harf juftliklari, birinchi harf, uzunlik: صُورَة ↔ سُورَة);
  - so'zlar soni bir xil (ibora ↔ ibora), ma'no uzunligi yaqin (uzunlikdan sezilmasin).
Eng o'xshash HARD_TOP nomzoddan 3 tasi tasodifiy — har jang boshqacha, lekin doim qiyin.
Nomzodlar: shu daraja + pastki darajalar (o'quvchiga tanish so'zlar).

Adolat: ma'nosi bir xil so'z (umumiy ma'no bo'lagi: «ish, amal» ↔ «amal, harakat») variant bo'lmaydi —
ikki to'g'ri javob chiqmaydi. Jangda ko'rinadigan ma'nodan grammatik izohlar ((X bob), (masdar)…) va
arabcha/transliteratsiya ishoralari ('muhtaram', o'zbekcha 'kitob' shundan) olib tashlanadi — javobni
sezdirmaydi. O'zlashma so'zlar (kitob, amal, vaqt: tarjimasida arabchaning o'zi bor) «arabcha → ma'no»
emas, «ma'no → arabcha» qilib so'raladi — tovushidan topib bo'lmaydi, arabchani o'qish kerak.
"""

import heapq
import random
import re
from difflib import SequenceMatcher
from functools import lru_cache

from services import vocab
from services import vocab_session as vs

KINDS = ("ar_uz", "uz_ar")  # tezkor jangda faqat matn (audio shovqinli joyda noqulay)
OPTIONS = 4
HARD_TOP = 6  # eng o'xshash shuncha nomzoddan 3 tasi tasodifiy

_ARABIC = re.compile("[" + chr(0x0600) + "-" + chr(0x06FF) + "]")  # arab yozuvi bloki
_QUOTED = re.compile(r"(?<![A-Za-zʻʼ'’])['‘’][A-Za-z]|[«»\"]")
_GRAMMAR = re.compile(
    r"\bbob\b|\bamr\b|ajvaf|muzoaf|mithal|naqis|mahmuz|majhul|maf'?ul|masdar|grammat|hijoziy|"
    r"lug'at shakli|o'zag|ko'plig|o'zbekcha|lahja|sheva|muzakkar|muannas",
    re.IGNORECASE,
)
_PAREN = re.compile(r"\s*\(([^()]*)\)")
_TR = str.maketrans(
    {"ā": "a", "â": "a", "á": "a", "ī": "i", "ū": "u", "o": "a", "w": "v", "ṣ": "s", "ḍ": "d", "ṭ": "t",
     "ẓ": "z", "ḥ": "h", "ʿ": "", "ʾ": "", "'": "", "’": "", "‘": "", "`": "", "ʻ": "", "ʼ": ""}
)


def meaning(w: dict) -> str:
    """Jangda ko'rinadigan ma'no: «·» dan keyingi qism, grammatik izohlar va arabcha/transliteratsiya
    ishoralari olib tashlanadi; mazmunni aniqlovchi izohlar ((rang), (ayol)) qoladi."""
    base = vs.split_uz(w.get("uz", ""))[0]

    def drop(m: re.Match) -> str:
        inner = m.group(1)
        if _ARABIC.search(inner) or _QUOTED.search(inner) or _GRAMMAR.search(inner):
            return ""
        return m.group(0)

    # Avval qavslar (ichida « · » bo'lishi mumkin: «(VII bob · u — lug'at shakli)»), keyin « · » dan keyingisi
    main = _PAREN.sub(drop, base).split(" · ")[0]
    main = re.sub(r"\s{2,}", " ", main).strip(" ,;·")
    return main or base


def senses(text: str) -> frozenset[str]:
    """Ma'no bo'laklari: «ish, amal» → {ish, amal}. Umumiy bo'lak — sinonim (ikkala variant to'g'ri)."""
    out = set()
    for part in re.split(r"[,;/]", text.lower()):
        p = re.sub(r"[^\w' ]", " ", part.replace("ʻ", "'").replace("’", "'"))
        p = re.sub(r"\s+", " ", p).strip()
        if p:
            out.add(p)
    return frozenset(out)


def _norm_latin(s: str) -> str:
    s = (s or "").lower().translate(_TR)
    for a, b in (("kh", "x"), ("th", "s"), ("dh", "z"), ("aa", "a"), ("ii", "i"), ("uu", "u"), ("q", "k")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z]", "", s)


def leaks(w: dict, text: str | None = None) -> bool:
    """Tarjimada arabcha so'zning o'zi bor (kitob ← kitāb, amal ← ʿamal, vaqt ← waqt)."""
    tr = _norm_latin(w.get("translit", ""))
    if tr.startswith("al") and len(tr) > 5:
        tr = tr[2:]
    if len(tr) < 3:
        return False
    for tok in re.split(r"[\s,;/()·.!?-]+", text if text is not None else meaning(w)):
        t = _norm_latin(tok)
        if len(t) >= 3 and SequenceMatcher(None, tr, t).ratio() >= 0.8:
            return True
    return False


def _bigrams(s: str) -> frozenset[str]:
    return frozenset(s[i : i + 2] for i in range(len(s) - 1)) or frozenset({s})


@lru_cache(maxsize=8)
def _index(level: str) -> tuple[dict[str, dict], dict[str, tuple[dict, ...]], tuple[dict, ...]]:
    """(kalit → belgilar, so'z turkumi → nomzodlar, hamma nomzodlar) — shu va pastki darajalar."""
    levels = vocab.LEVELS[: vocab.LEVELS.index(level) + 1] if level in vocab.LEVELS else vocab.LEVELS[:1]
    by_key: dict[str, dict] = {}
    for lv in reversed(levels):  # o'z darajasi birinchi
        for w in vocab.card_pool(lv):
            if w["key"] in by_key:
                continue
            m = meaning(w)
            by_key[w["key"]] = {
                "w": w,
                "key": w["key"],
                "ar": w["ar"],
                "pos": w.get("pos") or "",
                "root": w.get("root") or "",
                "pattern": w.get("pattern") or "",
                "topic": w.get("topic") or "",
                "nw": len(w["ar"].split()),
                "meaning": m,
                "senses": senses(m),
                "bi": _bigrams(w["key"]),
                "first": w["key"][:1],
                "len": len(w["key"]),
                "mlen": len(m),
                "leak": leaks(w, m),
                # Ma'nosida arabcha harf qolgan grammatik yozuvlar («muannasi كِلْتَا») — jangga yaramaydi
                "ok": not _ARABIC.search(m),
            }
    usable = [f for f in by_key.values() if f["ok"]]
    by_pos: dict[str, list[dict]] = {}
    for f in usable:
        by_pos.setdefault(f["pos"], []).append(f)
    return by_key, {k: tuple(v) for k, v in by_pos.items()}, tuple(usable)


def similarity(t: dict, c: dict, kind: str) -> float:
    """Chalg'ituvchi qanchalik «adashtiradi» — katta = qiyinroq."""
    s = 0.0
    if c["pos"] == t["pos"]:
        s += 4
    if t["root"] and c["root"] == t["root"]:
        s += 4
    if t["pattern"] and c["pattern"] == t["pattern"]:
        s += 2.5
    inter = len(t["bi"] & c["bi"])
    s += 3 * (2 * inter / (len(t["bi"]) + len(c["bi"])))
    if c["nw"] == t["nw"]:
        s += 2
    if c["first"] == t["first"]:
        s += 1
    if c["len"] == t["len"]:
        s += 1
    if t["topic"] and c["topic"] == t["topic"]:
        s += 1
    if kind == "ar_uz":
        s += 1.5 * (1 - min(1.0, abs(t["mlen"] - c["mlen"]) / max(t["mlen"], c["mlen"], 1)))
    return s


def _shown(f: dict, kind: str) -> str:
    return f["ar"] if kind == "uz_ar" else f["meaning"]


def _distractors(t: dict, kind: str, level: str, rnd: random.Random) -> list[str]:
    _, by_pos, everyone = _index(level)
    right = _shown(t, kind)
    norm = (lambda s: vocab.card_key(s)) if kind == "uz_ar" else (lambda s: s.lower().strip())
    picked: list[str] = []
    seen = {norm(right)}
    for pool in (by_pos.get(t["pos"], ()), everyone):  # avval shu turkumdan, yetmasa — hammasi
        ranked = heapq.nlargest(
            HARD_TOP * 4,
            (c for c in pool if c["key"] != t["key"] and not (c["senses"] & t["senses"])),
            key=lambda c: similarity(t, c, kind) + rnd.random() * 1.5,
        )
        top: list[str] = []
        for c in ranked:
            opt = _shown(c, kind)
            n = norm(opt)
            if not opt or n in seen:
                continue
            seen.add(n)
            top.append(opt)
            if len(top) + len(picked) >= HARD_TOP:
                break
        picked += rnd.sample(top, min(OPTIONS - 1 - len(picked), len(top)))
        if len(picked) >= OPTIONS - 1:
            break
    return picked


def question(w: dict, kind: str, level: str, rnd: random.Random) -> dict:
    by_key, _, _ = _index(level)
    t = by_key.get(w["key"])
    if t is None:  # nazariy holat — so'z indeksda yo'q
        return vs.question(w, kind, list(vocab.card_pool(level)), level, rnd)
    if kind == "ar_uz" and t["leak"]:
        kind = "uz_ar"  # o'zlashma so'z: tarjimasidan tovush bo'yicha topilmasin
    options = _distractors(t, kind, level, rnd) + [_shown(t, kind)]
    rnd.shuffle(options)
    return {
        "key": t["key"],
        "type": kind,
        "prompt": t["ar"] if kind == "ar_uz" else t["meaning"],
        "audio": "",
        "options": options,
        "answer": _shown(t, kind),
    }


def build(level: str, rnd: random.Random, n: int) -> list[dict]:
    """Darajaning lug'atidan n savol: turlari navbatma-navbat (o'zlashma so'z — «ma'no → arabcha»)."""
    by_key, _, _ = _index(level)
    pool = [w for w in vocab.card_pool(level) if by_key.get(w["key"], {}).get("ok", True)]
    words = rnd.sample(pool, min(n, len(pool)))
    return [question(w, KINDS[i % len(KINDS)], level, rnd) for i, w in enumerate(words)]
