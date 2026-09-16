"""Tinglab tushunish (K18.3) — LLM'siz, bepul: edge-tts jumla → tarjimani tanlash
yoki diktant (eshitganini yozish, o'xshashlik bali).

Talaffuz mashqi infrasi ustiga (drill.sentences): mavzu bo'yicha 10 jumla.
Klientga arabcha matn OLDINDAN berilmaydi — faqat audio (va variantlar);
javob serverda tekshiriladi, matn keyin ochiladi. Sessiya xotirada (2 soat).
"""

import random
import secrets
import time

from services import drill
from services.tutor import pronunciation_score
from services.vocab import load_level

SIZE = 10
CHOICES = 4
MIN_SCORED = 5
MAX_XP = 10
TTL = 2 * 3600
MAX_SESSIONS = 2000
KINDS = ("choice", "dictation")

_SESSIONS: dict[str, dict] = {}


def _distractors(item: dict, pool: list[str], rng: random.Random) -> list[str]:
    """3 ta boshqa tarjima — bir xil bo'lmagan, iloji boricha o'xshash uzunlikda."""
    correct = item["uz"]
    cands = [u for u in pool if u != correct]
    rng.shuffle(cands)
    # Uzunligi yaqinroqlarini oldinga — variantlar bir-biridan «ko'rinishda» ajralmasin
    cands.sort(key=lambda u: abs(len(u) - len(correct)) // 12)
    out: list[str] = []
    for u in cands:
        if u not in out:
            out.append(u)
        if len(out) == CHOICES - 1:
            break
    return out


def build(level: str, topic_id: str, kind: str, rng: random.Random | None = None) -> list[dict]:
    rng = rng or random.Random()
    kind = kind if kind in KINDS else "choice"
    items = drill.sentences(level, topic_id, SIZE, rng)
    if kind == "choice":
        levels = drill._levels_upto(level)
        pool = [
            (w.get("example_uz") or "").strip()
            for lv in levels[-2:]
            for w in load_level(lv)
            if (w.get("example_uz") or "").strip()
        ]
        pool = pool or [it["uz"] for it in items]
        for it in items:
            opts = _distractors(it, pool, rng) + [it["uz"]]
            rng.shuffle(opts)
            it["options"] = opts
            it["answer"] = opts.index(it["uz"])
    return items


def _sweep() -> None:
    now = time.time()
    for k in [k for k, d in _SESSIONS.items() if now - d["created"] > TTL]:
        _SESSIONS.pop(k, None)
    if len(_SESSIONS) > MAX_SESSIONS:
        for k in sorted(_SESSIONS, key=lambda k: _SESSIONS[k]["created"])[: len(_SESSIONS) - MAX_SESSIONS]:
            _SESSIONS.pop(k, None)


def create(user_id: int, level: str, topic_id: str, kind: str) -> tuple[str, dict]:
    _sweep()
    kind = kind if kind in KINDS else "choice"
    items = build(level, topic_id, kind)
    key = secrets.token_urlsafe(12)
    _SESSIONS[key] = {
        "user_id": user_id,
        "level": level,
        "topic": topic_id if topic_id in drill.TOPIC_BY_ID else "erkin",
        "kind": kind,
        "items": items,
        "scores": {},
        "created": time.time(),
    }
    return key, _SESSIONS[key]


def get(key: str, user_id: int) -> dict | None:
    d = _SESSIONS.get(key)
    return d if d and d["user_id"] == user_id else None


def public_items(d: dict) -> list[dict]:
    """Klientga: audio uchun matn EMAS — faqat indeks va (tanlash rejimida) variantlar."""
    out = []
    for i, it in enumerate(d["items"]):
        row = {"idx": i}
        if d["kind"] == "choice":
            row["options"] = it["options"]
        out.append(row)
    return out


def answer(key: str, user_id: int, idx: int, choice: int | None = None, text: str = "") -> dict | None:
    """Javobni tekshiradi; birinchi urinish bali saqlanadi (qayta urinish ballni o'zgartirmaydi)."""
    d = get(key, user_id)
    if not d or not (0 <= idx < len(d["items"])):
        return None
    it = d["items"][idx]
    if d["kind"] == "choice":
        if choice is None or not (0 <= choice < len(it["options"])):
            return None
        correct = choice == it["answer"]
        score = 100 if correct else 0
        result = {"correct": correct, "score": score, "answer": it["answer"]}
    else:
        ps = pronunciation_score(it["ar"], text or "")
        score = ps["score"]
        result = {"correct": score >= 80, "score": score, "words": ps["words"]}
    if idx not in d["scores"]:
        d["scores"][idx] = score
    result.update({"ar": it["ar"], "translit": it["translit"], "uz": it["uz"], "word": it["word"]})
    return result


def summary(key: str, user_id: int) -> dict | None:
    d = get(key, user_id)
    if not d:
        return None
    scores = [d["scores"].get(i, -1) for i in range(len(d["items"]))]
    done = [s for s in scores if s >= 0]
    avg = round(sum(done) / len(done)) if done else 0
    return {
        "topic": d["topic"],
        "kind": d["kind"],
        "level": d["level"],
        "scores": scores,
        "count": len(done),
        "score": avg,
        "items": [{"ar": it["ar"], "translit": it["translit"], "uz": it["uz"]} for it in d["items"]],
    }


def xp_for(avg: int, count: int) -> int:
    if count < MIN_SCORED:
        return 0
    return max(round(avg / 100 * MAX_XP), 1) if avg > 0 else 0


def finish(key: str, user_id: int) -> None:
    _SESSIONS.pop(key, None)
