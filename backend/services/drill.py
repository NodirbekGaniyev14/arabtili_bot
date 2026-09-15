"""Talaffuz mashqi (K17.5) — LLM'siz, bepul: lug'at misol jumlalari + Groq STT
+ o'xshashlik bali (tutor.pronunciation_score).

Mavzu (tutor.TOPICS) → o'quvchi darajasigacha bo'lgan lug'atdan mavzuga oid
10 ta harakatli misol jumla (transliti services/translit.py, audio edge-tts).
Har jumla: eshit → ayt → ball. Sessiya xotirada (`_DRILLS`, 2 soat): server
maqsad jumlani o'zi biladi — ballni klient soxtalashtira olmaydi.
"""

import random
import secrets
import time

from services.reference import normalize
from services.translit import translit
from services.tutor import TOPIC_BY_ID
from services.vocab import LEVELS, load_level

DRILL_SIZE = 10
MIN_SCORED = 5  # XP uchun kamida shuncha jumla aytilgan bo'lsin
MAX_XP = 10  # o'rtacha 100% → 10 XP; bir mavzu uchun kuniga bir marta
TTL = 2 * 3600
MAX_SESSIONS = 2000
GENERAL_POOL = 400  # mavzusiz to'ldirish: darajaning eng chastotali so'zlari

_DRILLS: dict[str, dict] = {}


def _levels_upto(level: str) -> list[str]:
    level = level.upper()
    if level not in LEVELS:
        level = "A0"
    return list(LEVELS[: LEVELS.index(level) + 1])


def _ok(w: dict) -> bool:
    ar = (w.get("example_ar") or "").strip()
    return 4 <= len(ar) <= 120 and bool(w.get("example_uz"))


def sentences(level: str, topic_id: str, n: int = DRILL_SIZE, rng: random.Random | None = None) -> list[dict]:
    """Mavzuga oid n ta jumla: avval o'quvchi darajasi, keyin pastroq darajalar;
    yetmasa — darajaning umumiy chastotali so'zlaridan."""
    rng = rng or random.Random()
    levels = _levels_upto(level)
    themes = set((TOPIC_BY_ID.get(topic_id) or {}).get("themes") or [])
    seen: set[str] = set()
    picked: list[dict] = []

    def take(pool: list[dict], k: int) -> None:
        pool = [w for w in pool if _ok(w) and normalize(w["example_ar"]) not in seen]
        for w in rng.sample(pool, min(k, len(pool))):
            seen.add(normalize(w["example_ar"]))
            picked.append(w)

    if themes:
        for lv in reversed(levels):  # o'z darajasi birinchi
            if len(picked) >= n:
                break
            take([w for w in load_level(lv) if w.get("theme") in themes], n - len(picked))
    if len(picked) < n:
        top = sorted(load_level(levels[-1]), key=lambda w: w.get("rank", 0))[:GENERAL_POOL]
        take(top, n - len(picked))
    if len(picked) < n and len(levels) > 1:
        take(load_level(levels[-2]), n - len(picked))

    return [
        {
            "ar": w["example_ar"].strip(),
            "translit": translit(w["example_ar"]),
            "uz": w["example_uz"].strip(),
            "word": {"ar": w["ar"], "translit": w.get("translit", ""), "uz": w.get("uz", "")},
        }
        for w in picked
    ]


def _sweep() -> None:
    now = time.time()
    dead = [k for k, d in _DRILLS.items() if now - d["created"] > TTL]
    for k in dead:
        _DRILLS.pop(k, None)
    if len(_DRILLS) > MAX_SESSIONS:
        for k in sorted(_DRILLS, key=lambda k: _DRILLS[k]["created"])[: len(_DRILLS) - MAX_SESSIONS]:
            _DRILLS.pop(k, None)


def create(user_id: int, level: str, topic_id: str) -> tuple[str, list[dict]]:
    _sweep()
    items = sentences(level, topic_id)
    key = secrets.token_urlsafe(12)
    _DRILLS[key] = {
        "user_id": user_id,
        "level": level,
        "topic": topic_id if topic_id in TOPIC_BY_ID else "erkin",
        "items": items,
        "scores": {},
        "created": time.time(),
    }
    return key, items


def get(key: str, user_id: int) -> dict | None:
    d = _DRILLS.get(key)
    return d if d and d["user_id"] == user_id else None


def target(key: str, user_id: int, idx: int) -> str:
    d = get(key, user_id)
    if not d or not (0 <= idx < len(d["items"])):
        return ""
    return d["items"][idx]["ar"]


def record(key: str, user_id: int, idx: int, score: int) -> None:
    """Har jumla uchun eng yaxshi urinish saqlanadi."""
    d = get(key, user_id)
    if d and 0 <= idx < len(d["items"]):
        d["scores"][idx] = max(d["scores"].get(idx, 0), score)


def summary(key: str, user_id: int) -> dict | None:
    d = get(key, user_id)
    if not d:
        return None
    scores = [d["scores"].get(i, -1) for i in range(len(d["items"]))]
    done = [s for s in scores if s >= 0]
    avg = round(sum(done) / len(done)) if done else 0
    return {
        "topic": d["topic"],
        "level": d["level"],
        "scores": scores,
        "count": len(done),
        "score": avg,
        "items": d["items"],
    }


def xp_for(avg: int, count: int) -> int:
    if count < MIN_SCORED:
        return 0
    return max(round(avg / 100 * MAX_XP), 1) if avg > 0 else 0


def finish(key: str, user_id: int) -> None:
    _DRILLS.pop(key, None)
