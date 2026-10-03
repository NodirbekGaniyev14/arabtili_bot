"""K31 Statistika sahifasi va VIP «Shaxsiy tahlil» (pages/Stats.tsx, Paywall tizeri).

Bepul: streak, taxminiy daraja, maqsad, 4 ko'nikma (O'qish / Tinglash / Yozish / Gapirish), lug'at, tarix.
VIP: 5 ta shaxsiy tahlildan 4 tasi — eng zaif ko'nikma, takrorlanadigan xatolar (arab tiliga xos turlar:
harakat, «ال», jins ـة, hamza, o'xshash harflar…), maqsad prognozi, haftalik reja. Birinchisi (daraja) bepul —
qiymatini ko'rsatib, qolganiga qiziqtiradi. VIP bo'lmaganga yopiq tahlil QIYMATI yuborilmaydi (faqat tavsif).

Hamma natijalar mavjud jadvallardan olinadi (yangi jadval yo'q); ballar 0-100.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from difflib import SequenceMatcher
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache

from sqlalchemy import or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    AnswerLog,
    Battle,
    DailySpeaking,
    DrillResult,
    ExamAttempt,
    ListeningResult,
    LiveSession,
    MockResult,
    Plan,
    Progress,
    TraceResult,
    TutorMistake,
    User,
    UserWord,
    WritingResult,
    XpLog,
)
from services.stats import TASHKENT_OFFSET, _local_date, _today, completed_lesson_ids, resolve_streak

PERIODS: dict[str, int | None] = {"week": 7, "month": 30, "3m": 90, "all": None}
SKILLS = ("reading", "listening", "writing", "speaking")
INSIGHT_DAYS = 90  # tahlillar shu oynadan (davr tanlovidan qat'i nazar — barqaror bo'lsin)
HISTORY_LIMIT = 80
MIN_MISTAKES = 5
MIN_LESSONS_FORECAST = 3
MATURE_DAYS = 21  # Anki «mustahkam» chegarasi
MAX_WEEKLY_LESSONS = 7  # rejada bundan ko'p dars tavsiya qilinmaydi (real yuklama)


# ─────────────────────────── natijalar (ko'nikma bo'yicha) ───────────────────────────


@dataclass
class Result:
    at: datetime  # naive UTC
    skill: str  # reading | listening | writing | speaking | vocab | exam
    title: str
    score: int | None
    xp: int = 0


def _topic_title(topic_id: str) -> str:
    from services import tutor

    t = tutor.TOPIC_BY_ID.get(topic_id)
    return t["title_uz"] if t else ""


def _mock_title(mock_id: str) -> str:
    from services import tutor

    m = tutor.MOCK_BY_ID.get(mock_id)
    return m["title_uz"] if m else "Mock imtihon"


def _lesson_title(lesson_id: str) -> str:
    from services.curriculum import load_curriculum

    meta = load_curriculum().get(lesson_id) or {}
    return meta.get("title_uz") or lesson_id


def _join(*parts: str) -> str:
    return " · ".join(p for p in parts if p)


async def results(session: AsyncSession, user_id: int, since: datetime | None) -> list[Result]:
    """Foydalanuvchining barcha baholangan mashqlari (eng yangisi birinchi)."""
    from services.curriculum import load_curriculum

    def after(col):
        return col >= since if since is not None else true()

    out: list[Result] = []
    v2 = load_curriculum()

    for p in (
        await session.execute(select(Progress).where(Progress.user_id == user_id, after(Progress.completed_at)))
    ).scalars():
        if p.lesson_id not in v2 or not p.total:
            continue
        out.append(Result(p.completed_at, "reading", _join("Dars", _lesson_title(p.lesson_id)),
                          round(100 * p.correct / p.total), p.xp_earned or 0))

    for e in (
        await session.execute(
            select(ExamAttempt).where(
                ExamAttempt.user_id == user_id, ExamAttempt.finished_at.is_not(None), after(ExamAttempt.finished_at)
            )
        )
    ).scalars():
        if e.kind == "level":
            # Daraja imtihoni — har ko'nikma alohida bal (0-100); tarixda bitta yozuv
            for skill, sc in zip(SKILLS, (e.score_reading, e.score_listening, e.score_writing, e.score_speaking)):
                out.append(Result(e.finished_at, f"_{skill}", "", sc))
            out.append(Result(e.finished_at, "exam", _join("Daraja imtihoni", e.level), e.total_score))
        else:
            out.append(Result(e.finished_at, "exam", _join("Oraliq imtihon", e.level, f"{e.checkpoint}%"),
                              e.total_score))

    for r in (
        await session.execute(
            select(ListeningResult).where(ListeningResult.user_id == user_id, after(ListeningResult.created_at))
        )
    ).scalars():
        kind = "diktant" if r.kind == "dictation" else ""
        out.append(Result(r.created_at, "listening", _join("Tinglash", _topic_title(r.topic), kind), r.score, r.xp))

    for r in (
        await session.execute(
            select(WritingResult).where(WritingResult.user_id == user_id, after(WritingResult.updated_at))
        )
    ).scalars():
        out.append(Result(r.updated_at or r.created_at, "writing", "Yozuv (xattotlik) mashqi", r.score, r.xp))

    for r in (
        await session.execute(select(TraceResult).where(TraceResult.user_id == user_id, after(TraceResult.created_at)))
    ).scalars():
        out.append(Result(r.created_at, "writing", _join("Harf chizish", f"{r.count} harf"), r.avg, r.xp))

    for r in (
        await session.execute(select(DrillResult).where(DrillResult.user_id == user_id, after(DrillResult.created_at)))
    ).scalars():
        out.append(Result(r.created_at, "speaking", _join("Talaffuz", _topic_title(r.topic)), r.score, r.xp))

    for r in (
        await session.execute(select(MockResult).where(MockResult.user_id == user_id, after(MockResult.created_at)))
    ).scalars():
        out.append(Result(r.created_at, "speaking", _join("Mock imtihon", _mock_title(r.mock_id)), r.score, r.xp))

    for r in (
        await session.execute(
            select(DailySpeaking).where(DailySpeaking.user_id == user_id, after(DailySpeaking.created_at))
        )
    ).scalars():
        out.append(Result(r.created_at, "speaking", "Kunlik savol", r.score, r.xp))

    for r in (
        await session.execute(
            select(LiveSession).where(
                LiveSession.user_id == user_id, LiveSession.seconds >= 20, after(LiveSession.created_at)
            )
        )
    ).scalars():
        mins = max(1, round(r.seconds / 60))
        out.append(Result(r.created_at, "speaking", _join("Jonli AI suhbat", _topic_title(r.topic), f"{mins} daq"),
                          None))

    for b in (
        await session.execute(
            select(Battle).where(or_(Battle.p1_id == user_id, Battle.p2_id == user_id), after(Battle.created_at))
        )
    ).scalars():
        me1 = b.p1_id == user_id
        correct = b.p1_correct if me1 else b.p2_correct
        won = b.winner == (1 if me1 else 2)
        out.append(Result(b.created_at, "vocab", _join("Oktagon jangi", "g'alaba" if won else ""),
                          min(100, correct * 10)))

    out.sort(key=lambda r: r.at, reverse=True)
    return out


def skill_summary(res: list[Result]) -> dict[str, dict]:
    """Ko'nikma → {score: o'rtacha | None, count, last, delta (oxirgi 3 ta − oldingi 3 ta)}."""
    out: dict[str, dict] = {}
    for skill in SKILLS:
        scores = [r.score for r in res if r.skill in (skill, f"_{skill}") and r.score is not None]
        count = sum(1 for r in res if r.skill == skill)
        avg = round(sum(scores) / len(scores)) if scores else None
        delta = None
        if len(scores) >= 4:
            recent, before = scores[:3], scores[3:6]
            delta = round(sum(recent) / len(recent) - sum(before) / len(before))
        out[skill] = {"score": avg, "count": count, "last": scores[0] if scores else None, "delta": delta}
    return out


# ─────────────────────────── xatolar tasnifi (arab tiliga xos) ───────────────────────────

_HARAKAT = re.compile("[" + chr(0x064B) + "-" + chr(0x065F) + chr(0x0670) + chr(0x0640) + "]")
_ARABIC = re.compile("[" + chr(0x0621) + "-" + chr(0x064A) + "]")
_HAMZA = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ؤ": "و", "ئ": "ي", "ء": None})
# Talaffuzi yaqin harflar — o'zbek o'quvchisi eng ko'p adashtiradigan juftlar
_PAIRS = {
    frozenset(p)
    for p in (("ح", "ه"), ("ح", "خ"), ("س", "ص"), ("ت", "ط"), ("د", "ض"), ("ذ", "ز"), ("ز", "ظ"), ("ذ", "ظ"),
              ("ض", "ظ"), ("ك", "ق"), ("ث", "س"), ("غ", "خ"), ("ع", "ا"), ("ع", "أ"))
}

# (sarlavha, belgi, maslahat) — misollar to'liq harakatli, tekshirilgan
MISTAKE_CATS: dict[str, tuple[str, str, str]] = {
    "harakat": ("Harakatlar (unli belgilar)", "ـَـِـُ",
                "Harakatni so'z oxirigacha qo'ying — u gapdagi vazifani bildiradi: "
                "الكِتَابُ (ega) / الكِتَابَ (to'ldiruvchi)."),
    "al": ("«ال» artikli", "ال",
           "Aniq narsa — «ال» bilan: البَيْتُ (shu uy); noaniq — tanvin bilan: بَيْتٌ (bir uy)."),
    "jins": ("Jins moslashuvi (ـة)", "ة",
             "Muannas otga sifat ham ـة bilan moslashadi: سَيَّارَةٌ جَمِيلَةٌ."),
    "hamza": ("Hamza yozilishi", "ء",
              "So'z boshida fatha va dammada hamza tepada, kasrada pastda: أَنَا، أُمّ، إِسْلَام."),
    "harflar": ("O'xshash harflar", "ح/ه",
                "Talaffuzi yaqin juftlar: ح–ه، س–ص، ت–ط، د–ض، ذ–ز–ظ، ك–ق. Har birini alohida tinglab, farqlab ayting."),
    "fel": ("Fe'l shakllari", "فِعْل",
            "Fe'l shaxsga qarab o'zgaradi: أَذْهَبُ (men), تَذْهَبُ (sen), يَذْهَبُ (u)."),
    "koplik": ("Ko'plik va juftlik", "جَمْع",
               "Ko'plikning ko'pi singan shaklda: كِتَاب ← كُتُب، بَيْت ← بُيُوت — so'z bilan birga yodlang."),
    "predlog": ("Old ko'makchilar", "فِي",
                "Fe'l bilan keladigan ko'makchini birga yodlang: ذَهَبَ إِلَى (ga bordi), "
                "جَلَسَ عَلَى (ustiga o'tirdi), سَكَنَ فِي (da yashadi)."),
    "meaning": ("So'z tanlash va ma'nosi", "؟",
                "Qiyin so'zlarni Lug'at bo'limida takrorlang — kunlik 5 daqiqalik takror ularni mustahkamlaydi."),
    "boshqa": ("Gap tuzilishi", "…",
               "Ustoz tuzatgan gaplarni Xatolar daftarida ovoz chiqarib qayta ayting."),
}

_NOTE_RULES: list[tuple[str, re.Pattern]] = [
    ("harakat", re.compile(r"harakat|fatha|kasra|damma|sukun|tanvin|i'rob|irob", re.I)),
    ("al", re.compile(r"artikl|«ال»|\bال\b|aniqlik", re.I)),
    ("jins", re.compile(r"jins|muannas|muzakkar|ـة|ta marbuta", re.I)),
    ("hamza", re.compile(r"hamza", re.I)),
    ("fel", re.compile(r"fe['’]l|zamon|tuslan|shaxs|ماض|مضارع|mozi|muzori", re.I)),
    ("koplik", re.compile(r"ko['’]plik|jam['’]|juftlik|muthanna|مثنى|جمع", re.I)),
    ("predlog", re.compile(r"ko['’]makchi|predlog|حرف جر|harf[- ]jar", re.I)),
]


_PUNCT = re.compile(r"[.,!?;:\"'«»()\[\]\-–—…؟،؛]")


def _words(s: str) -> list[str]:
    # \w harakatni (birikuvchi belgi) olib tashlardi — faqat tinish belgilari
    return _PUNCT.sub(" ", s or "").split()


def _strip_al(w: str) -> str:
    return w[2:] if w.startswith("ال") and len(w) > 3 else w


_PREPS = {"الى", "إلى", "في", "على", "من", "عن", "مع", "ب", "ل"}
_VERB_SUFFIX = ("ت", "وا", "ن", "نا", "تم", "تن", "ي")
_VERB_PREFIX = ("أ", "ت", "ي", "ن")


def _verb_affix(x: str, y: str) -> bool:
    """Bir so'z ikkinchisidan fe'l qo'shimchasi bilan farq qiladi: ذهب ↔ ذهبت، أذهب ↔ تذهب."""
    short, long_ = sorted((x, y), key=len)
    if len(short) >= 2 and long_.startswith(short) and long_[len(short):] in _VERB_SUFFIX:
        return True
    return len(x) == len(y) >= 3 and x[1:] == y[1:] and x[0] in _VERB_PREFIX and y[0] in _VERB_PREFIX


def classify(said: str, fixed: str, note: str = "") -> tuple[str, str] | None:
    """(tur, tafsilot) — arabcha xato turini matn farqidan, bo'lmasa izohdan aniqlaydi. Bir xil → None."""
    if not _ARABIC.search(fixed or "") or not _ARABIC.search(said or ""):
        return None  # o'zbekcha/lotincha javob — arabcha xato turi emas
    a, b = " ".join(_words(said)), " ".join(_words(fixed))
    if not a or a == b:
        return None
    ba, bb = _HARAKAT.sub("", a), _HARAKAT.sub("", b)
    if len(ba.replace(" ", "")) <= 1 < len(bb.replace(" ", "")):
        return None  # bitta harf — «bilmayman» belgisi, tahlilni buzmasin
    if ba == bb:
        return ("harakat", "")
    wa, wb = ba.split(), bb.split()
    if len(wa) == len(wb):
        if [_strip_al(w) for w in wa] == [_strip_al(w) for w in wb]:
            return ("al", "")
        diff = [(x, y) for x, y in zip(wa, wb) if x != y]
        if diff and all(x + "ة" == y or y + "ة" == x for x, y in diff):
            return ("jins", "")
        if ba.translate(_HAMZA) == bb.translate(_HAMZA):
            return ("hamza", "")
        if len(ba) == len(bb):
            swaps = {frozenset((x, y)) for x, y in zip(ba, bb) if x != y}
            if swaps and swaps <= _PAIRS:
                pair = sorted(swaps, key=lambda s: "".join(sorted(s)))[0]
                return ("harflar", "–".join(sorted(pair)))
        if any(_verb_affix(x, y) for x, y in diff):
            return ("fel", "")
    elif len(wb) == len(wa) + 1:
        extra = [w for w in wb if w not in wa]
        if len(extra) == 1 and extra[0].translate(_HAMZA) in {p.translate(_HAMZA) for p in _PREPS}:
            return ("predlog", "")
        if len(extra) == 1 and extra[0].translate(_HAMZA) == "ان":
            return ("fel", "")
    for cat, rx in _NOTE_RULES:
        if rx.search(note or ""):
            return (cat, "")
    if len(wa) == len(wb) == 1 and SequenceMatcher(None, ba, bb).ratio() < 0.5:
        return ("meaning", "")  # butunlay boshqa so'z — so'z xotirasi
    return ("boshqa", "")


async def mistake_stats(session: AsyncSession, user_id: int, since: datetime) -> dict:
    """Xato turlari: {total, top: [{id, title, mark, tip, count, pair, example: {said, fixed}}]}."""
    counts: Counter[str] = Counter()
    pairs: Counter[str] = Counter()
    examples: dict[str, dict] = {}

    def add(cat: str, detail: str, said: str, fixed: str) -> None:
        counts[cat] += 1
        if detail:
            pairs[detail] += 1
        # Misol — faqat haqiqiy tuzatish (mock'dagi «ideal javob» butunlay boshqa gap bo'lishi mumkin)
        if cat not in examples and SequenceMatcher(None, _HARAKAT.sub("", said), _HARAKAT.sub("", fixed)).ratio() >= 0.5:
            examples[cat] = {"said": said[:80], "fixed": fixed[:80]}

    for m in (
        await session.execute(
            select(TutorMistake).where(TutorMistake.user_id == user_id, TutorMistake.created_at >= since)
        )
    ).scalars():
        c = classify(m.said_ar, m.fixed_ar, m.note_uz)
        if c:
            add(c[0], c[1], m.said_ar, m.fixed_ar)

    for a in (
        await session.execute(select(AnswerLog).where(AnswerLog.user_id == user_id, AnswerLog.created_at >= since))
    ).scalars():
        if not _ARABIC.search(a.expected or ""):
            # Arabcha → o'zbekcha tarjima: ma'no xatosi
            if a.given.strip():
                add("meaning", "", a.given, a.expected)
            continue
        c = classify(a.given, a.expected)
        if c:
            add(c[0], c[1], a.given, a.expected)

    top = []
    # «Gap tuzilishi» (aniqlanmagan) — faqat boshqa tur bo'lmasa birinchi chiqadi
    ranked = sorted(counts.items(), key=lambda kv: (kv[0] == "boshqa", -kv[1]))
    for cat, n in ranked[:3]:
        title, mark, tip = MISTAKE_CATS[cat]
        top.append({
            "id": cat, "title": title, "mark": mark, "tip": tip, "count": n,
            "pair": pairs.most_common(1)[0][0] if cat == "harflar" and pairs else "",
            "example": examples.get(cat, {}),
        })
    return {"total": sum(counts.values()), "top": top}


# ─────────────────────────── kurs holati: daraja, maqsad, prognoz ───────────────────────────


def _lesson_ids() -> list[str]:
    from services.curriculum import load_curriculum, lesson_order

    cur = load_curriculum()
    return [lid for lid in lesson_order() if cur[lid]["type"] == "lesson"]


def course_position(done: set[str], start_lesson: str) -> dict:
    """Joriy daraja (keyingi tugatilmagan dars darajasi) va o'sha darajadagi ulush."""
    from services.course import LEVELS, level_of, next_lesson

    nxt = next_lesson(done, start_lesson)
    ids = _lesson_ids()
    if nxt:
        level = level_of(nxt["id"])
    else:
        passed = [lid for lid in ids if lid in done]
        level = level_of(passed[-1]) if passed else "A0"
    start_idx = ids.index(start_lesson) if start_lesson in ids else 0
    in_level = [(i, lid) for i, lid in enumerate(ids) if level_of(lid) == level]
    counted = [lid for i, lid in in_level if lid in done or i < start_idx]
    return {
        "level": level,
        "level_index": LEVELS.index(level) if level in LEVELS else 0,
        "done": len(counted),
        "total": len(in_level),
        "percent": round(100 * len(counted) / len(in_level)) if in_level else 0,
        "next": nxt,
    }


def goal_progress(done: set[str], start_lesson: str, target: str) -> dict:
    """Maqsad darajasigacha bo'lgan yo'l: tugatilgan (yoki joylashtirishda o'tkazib yuborilgan) / jami dars."""
    from services.course import LEVELS, level_of

    ids = _lesson_ids()
    t_idx = LEVELS.index(target) if target in LEVELS else len(LEVELS) - 1
    path = [lid for lid in ids if LEVELS.index(level_of(lid)) <= t_idx]
    start_idx = ids.index(start_lesson) if start_lesson in ids else 0
    covered = [lid for i, lid in enumerate(path) if lid in done or i < start_idx]
    remaining = len(path) - len(covered)
    return {
        "target": target,
        "total": len(path),
        "covered": len(covered),
        "remaining": remaining,
        "percent": round(100 * len(covered) / len(path)) if path else 0,
    }


async def lesson_pace(session: AsyncSession, user_id: int, today: date) -> float:
    """Oxirgi 4 haftada BIRINCHI marta o'tilgan darslar / hafta."""
    rows = (
        await session.execute(
            select(Progress.lesson_id, Progress.completed_at).where(Progress.user_id == user_id, Progress.passed == 1)
        )
    ).all()
    first: dict[str, datetime] = {}
    for lid, at in rows:
        if lid not in first or at < first[lid]:
            first[lid] = at
    cutoff = today - timedelta(days=28)
    recent = sum(1 for at in first.values() if _local_date(at) > cutoff)
    return round(recent / 4, 1)


def forecast(goal: dict, pace: float, target_date: str, today: date) -> dict:
    """Maqsadga necha haftada yetadi va belgilangan sanaga ulguradimi."""
    remaining = goal["remaining"]
    if remaining <= 0:
        return {"done": True, "weeks": 0, "pace": pace, "on_track": True, "need_pace": 0, "days_left": None}
    weeks = math.ceil(remaining / pace) if pace > 0 else None
    days_left = None
    need_pace = None
    on_track = None
    try:
        td = date.fromisoformat(target_date) if target_date else None
    except ValueError:
        td = None
    if td:
        days_left = (td - today).days
        if days_left > 0:
            need_pace = round(remaining / (days_left / 7), 1)
            on_track = pace >= need_pace if pace > 0 else False
        else:
            on_track = False
    return {"done": False, "weeks": weeks, "pace": pace, "on_track": on_track, "need_pace": need_pace,
            "days_left": days_left, "remaining": remaining}


# ─────────────────────────── lug'at ───────────────────────────


@lru_cache(maxsize=1)
def _word_levels() -> dict[str, str]:
    """normalize(ar) → daraja (A0…B2): lug'at bazasi + v2 dars kartalari."""
    from services.curriculum import load_curriculum, load_lesson_v2
    from services.reference import normalize
    from services.vocab import all_words

    out: dict[str, str] = {}
    for w in all_words():
        key = normalize(w.get("ar") or "")
        if key and w.get("level"):
            out.setdefault(key, w["level"])
    for lid, meta in load_curriculum().items():
        lesson = load_lesson_v2(lid) or {}
        for c in lesson.get("srs_cards", []):
            key = normalize(c.get("front") or "")
            if key:
                out.setdefault(key, meta.get("level", "A0"))
        for v in lesson.get("vocabulary", []):
            key = normalize(v.get("ar") or "")
            if key:
                out.setdefault(key, meta.get("level", "A0"))
    return out


async def vocab_stats(session: AsyncSession, user_id: int, today: date) -> dict:
    from services.course import LEVELS
    from services.reference import normalize

    cards = (await session.execute(select(UserWord).where(UserWord.user_id == user_id))).scalars().all()
    levels_map = _word_levels()
    by_level: Counter[str] = Counter()
    stages = {"new": 0, "learning": 0, "mature": 0}
    reviewed = recalled = 0
    due = 0
    for c in cards:
        lvl = levels_map.get(normalize(c.ar))
        by_level[lvl if lvl in LEVELS else "other"] += 1
        if (c.reps or 0) == 0 and (c.lapses or 0) == 0:
            stages["new"] += 1
        elif (c.interval_days or 0) >= MATURE_DAYS:
            stages["mature"] += 1
        else:
            stages["learning"] += 1
        if (c.reps or 0) > 0 or (c.lapses or 0) > 0:
            reviewed += 1
            recalled += 1 if (c.reps or 0) > 0 else 0
        if c.due_date and c.due_date <= today.isoformat():
            due += 1
    hardest = sorted((c for c in cards if (c.lapses or 0) > 0), key=lambda c: (-c.lapses, c.ar))[:5]
    return {
        "total": len(cards),
        "due": due,
        "retention": round(100 * recalled / reviewed) if reviewed else None,
        "stages": stages,
        "levels": [{"level": lv, "count": by_level[lv]} for lv in [*LEVELS, "other"] if by_level[lv]],
        "hardest": [{"ar": c.ar, "uz": c.uz, "lapses": c.lapses} for c in hardest],
    }


# ─────────────────────────── streak haftasi ───────────────────────────


async def streak_block(session: AsyncSession, user_id: int, today: date) -> dict:
    days = {_local_date(dt) for dt in (await session.execute(select(XpLog.created_at).where(XpLog.user_id == user_id))).scalars()}
    streak, freezes = await resolve_streak(session, user_id, days, today)
    monday = today - timedelta(days=today.weekday())
    week = [{"day": (monday + timedelta(days=i)).isoformat(), "active": (monday + timedelta(days=i)) in days,
             "today": monday + timedelta(days=i) == today, "future": monday + timedelta(days=i) > today}
            for i in range(7)]
    return {"days": streak, "freezes": freezes, "week": week, "today_done": today in days}


# ─────────────────────────── shaxsiy tahlil (5 ta) ───────────────────────────

SKILL_UZ = {"reading": "O'qish", "listening": "Tinglash", "writing": "Yozish", "speaking": "Gapirish"}
SKILL_TIP = {
    "reading": "Har kuni 1 ta dars — mikro-testdagi xatolar avtomatik takrorga tushadi.",
    "listening": "Kuniga 1 ta tinglash mashqi (10 jumla) bu farqni 2–3 haftada yopadi.",
    "writing": "Har 2 kunda yozuv mashqi + harf chizish: qo'l harflarni tez «eslaydi».",
    "speaking": "Haftasiga 3 marta 5 daqiqalik jonli AI suhbat — eng tez o'sadigan ko'nikma.",
}
SKILL_ACTION = {"reading": "lesson", "listening": "listen", "writing": "writing", "speaking": "live"}

INSIGHT_META: dict[str, tuple[str, str, str]] = {
    # id: (sarlavha, belgi, VIP bo'lmaganga tavsif — nimani ochadi)
    "level": ("Hozirgi darajangiz", "📍", "Kurs bo'yicha aniq o'rningiz"),
    "weak": ("Eng zaif ko'nikmangiz", "🎯", "Qaysi ko'nikma orqada qolayotganini aniq ko'rsatadi"),
    "mistakes": ("Takrorlanadigan xatolaringiz", "✏️", "Harakat, «ال», jins, o'xshash harflar — qaysi biri ko'p"),
    "forecast": ("Maqsad prognozi", "📈", "Maqsad darajangizga qachon yetishingiz va sanaga ulgurishingiz"),
    "plan": ("Sizga moslangan haftalik reja", "🗓", "Zaif joylaringizdan tuzilgan aniq haftalik reja"),
}


def _insight(iid: str, state: str, **kw) -> dict:
    title, icon, teaser = INSIGHT_META[iid]
    return {"id": iid, "title": title, "icon": icon, "state": state, "teaser": teaser, **kw}


def build_insights(*, vip: bool, pos: dict, skills90: dict, mistakes: dict, fc: dict, goal: dict,
                   lessons_done: int, vocab: dict) -> dict:
    items: list[dict] = []

    # 1) Daraja — hammaga ochiq (qiymat ko'rinadi: tahlil foydasini his qildiradi)
    nxt = pos.get("next") or {}
    items.append(_insight(
        "level", "open",
        value=f"{pos['level']} · {pos['percent']}%",
        detail=f"{pos['level']} darajasining {pos['done']}/{pos['total']} darsi o'tilgan."
               + (f" Keyingisi: «{nxt.get('title')}»." if nxt.get("title") else ""),
    ))

    measured = {s: v["score"] for s, v in skills90.items() if v["score"] is not None}

    def gated(iid: str, ready: bool, need: str, have: int, want: int, **open_kw) -> dict:
        if not vip:
            return _insight(iid, "vip")
        if not ready:
            return _insight(iid, "data", need=need, have=min(have, want), want=want)
        return _insight(iid, "open", **open_kw)

    # 2) Eng zaif ko'nikma
    weak = min(measured, key=measured.get) if len(measured) >= 2 else None
    others = ", ".join(f"{SKILL_UZ[s]} {v}%" for s, v in sorted(measured.items(), key=lambda kv: -kv[1]) if s != weak)
    items.append(gated(
        "weak", weak is not None, "Kamida 2 ko'nikmada natija kerak — tinglash yoki talaffuz mashqini bajaring",
        len(measured), 2,
        value=f"{SKILL_UZ.get(weak, '')} · {measured.get(weak, 0)}%" if weak else "",
        detail=(f"Boshqalari: {others}. " if others else "") + SKILL_TIP.get(weak or "", ""),
        skill=weak or "", action=SKILL_ACTION.get(weak or "", ""),
    ))

    # 3) Xatolar
    top = mistakes["top"]
    items.append(gated(
        "mistakes", mistakes["total"] >= MIN_MISTAKES and bool(top),
        f"Darslar va ustoz bilan mashq qiling — {MIN_MISTAKES} ta xato yig'ilganda tahlil tayyor bo'ladi",
        mistakes["total"], MIN_MISTAKES,
        value=f"{top[0]['title']} · {top[0]['count']} marta" if top else "",
        detail=top[0]["tip"] if top else "",
        top=top, action="mistakes",
    ))

    # 4) Prognoz
    target = goal["target"]
    if fc.get("done"):
        fc_value, fc_detail = f"{target} — maqsadga yetdingiz 🎉", "Keyingi darajani maqsad qilib qo'yish vaqti keldi."
    elif fc.get("weeks") and fc["weeks"] > 104:
        fc_value = f"{target} ga hozirgi tezlikda 2 yildan ko'p"
        fc_detail = (f"Tezligingiz: haftasiga {fc['pace']:g} dars, {fc['remaining']} dars qoldi. "
                     f"Haftasiga 5 dars bilan ~{math.ceil(fc['remaining'] / 5)} haftada yetasiz.")
        if fc.get("need_pace") is not None and not fc.get("on_track"):
            fc_detail += f" Belgilangan sanaga ulgurish uchun haftasiga {fc['need_pace']:g} dars kerak."
    elif fc.get("weeks"):
        fc_value = f"{target} ga ~{fc['weeks']} hafta"
        fc_detail = f"Tezligingiz: haftasiga {fc['pace']:g} dars, {fc['remaining']} dars qoldi."
        if fc.get("need_pace") is not None:
            fc_detail += (" Belgilangan sanaga ulgurasiz ✓" if fc.get("on_track")
                          else f" Sanaga ulgurish uchun haftasiga {fc['need_pace']:g} dars kerak.")
    else:
        weeks3 = math.ceil(fc.get("remaining", goal["remaining"]) / 3) if goal["remaining"] else 0
        fc_value = "Oxirgi 4 haftada dars yo'q"
        fc_detail = f"Haftasiga 3 dars bilan {target} ga ~{weeks3} haftada yetasiz."
    items.append(gated(
        "forecast", lessons_done >= MIN_LESSONS_FORECAST,
        f"Prognoz uchun kamida {MIN_LESSONS_FORECAST} ta dars tugating", lessons_done, MIN_LESSONS_FORECAST,
        value=fc_value, detail=fc_detail,
    ))

    # 5) Haftalik reja — zaif ko'nikma, tezlik, xatolar, takror kartalaridan
    plan: list[dict] = []
    per_week = 3
    need = math.ceil(fc["need_pace"]) if fc.get("need_pace") else 0
    if need:
        per_week = max(3, min(MAX_WEEKLY_LESSONS, need))
    lesson_text = f"Haftasiga {per_week} ta dars"
    if need > MAX_WEEKLY_LESSONS:
        lesson_text += f" (sanaga ulgurish uchun ~{need} kerak — sanani surish ham mumkin)"
    plan.append({"icon": "📚", "text": lesson_text, "action": "lesson"})
    if weak:
        plan.append({
            "icon": {"reading": "📖", "listening": "🎧", "writing": "✍️", "speaking": "🎙️"}[weak],
            "text": {"reading": "Darslarni qayta ishlash — 2 marta",
                     "listening": "Tinglash mashqi — 3 marta",
                     "writing": "Yozuv mashqi — 2 marta",
                     "speaking": "Jonli AI suhbat — 3 × 5 daqiqa"}[weak],
            "action": SKILL_ACTION[weak],
        })
    if top:
        plan.append({"icon": "✏️", "text": f"Xatolar daftari: {top[0]['title'].lower()} — 10 daqiqa",
                     "action": "mistakes"})
    if vocab["due"] > 0:
        plan.append({"icon": "🔁", "text": f"Lug'at takrori — kuniga {min(vocab['due'], 20)} karta",
                     "action": "review"})
    items.append(gated(
        "plan", lessons_done >= 1, "Birinchi darsni tugating — reja shu asosda tuziladi", lessons_done, 1,
        value=f"{len(plan)} ta vazifa", detail="Har hafta natijalaringizga qarab yangilanadi.", plan=plan,
    ))

    unlocked = sum(1 for i in items if i["state"] == "open")
    return {"unlocked": unlocked, "total": len(items), "items": items}


# ─────────────────────────── yig'ma javob ───────────────────────────


def _since(period: str, now: datetime) -> datetime | None:
    days = PERIODS.get(period)
    return now - timedelta(days=days) if days else None


async def overview(session: AsyncSession, user: User, period: str = "month") -> dict:
    from services import billing

    if period not in PERIODS:
        period = "month"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    today = _today()
    vip = billing.is_vip(user)

    plan = (
        await session.execute(select(Plan).where(Plan.user_id == user.id).order_by(Plan.id.desc()).limit(1))
    ).scalar_one_or_none()
    start_lesson = plan.start_lesson if plan else "a0-01"
    target = (plan.target_level if plan else "") or "B1"
    target_date = plan.target_date if plan else ""

    done = await completed_lesson_ids(session, user.id)
    pos = course_position(done, start_lesson)
    goal = goal_progress(done, start_lesson, target)
    pace = await lesson_pace(session, user.id, today)
    fc = forecast(goal, pace, target_date, today)

    since90 = now - timedelta(days=INSIGHT_DAYS)
    res_all = await results(session, user.id, None)
    res_period = [r for r in res_all if (s := _since(period, now)) is None or r.at >= s]
    res_90 = [r for r in res_all if r.at >= since90]
    skills_period = skill_summary(res_period)
    skills90 = skill_summary(res_90)

    vocab = await vocab_stats(session, user.id, today)
    streak = await streak_block(session, user.id, today)
    course_ids = set(_lesson_ids())
    lessons_done = len(done & course_ids)

    insights = build_insights(
        vip=vip, pos=pos, skills90=skills90,
        mistakes=await mistake_stats(session, user.id, since90) if vip else {"total": 0, "top": []},
        fc=fc, goal=goal, lessons_done=lessons_done, vocab=vocab,
    )

    days_left = None
    if target_date:
        try:
            days_left = (date.fromisoformat(target_date) - today).days
        except ValueError:
            days_left = None

    history = [
        {"at": (r.at + TASHKENT_OFFSET).isoformat(timespec="minutes"), "skill": r.skill, "title": r.title,
         "score": r.score, "xp": r.xp}
        for r in res_period if not r.skill.startswith("_")
    ][:HISTORY_LIMIT]

    return {
        "period": period,
        "vip": vip,
        "streak": streak,
        "level": {k: v for k, v in pos.items() if k != "next"},
        "skills": skills_period,
        "skills_90": {s: v["score"] for s, v in skills90.items()},
        "goal": {**goal, "current": pos["level"], "target_date": target_date, "days_left": days_left},
        "vocab": vocab,
        "insights": insights,
        "history": history,
    }
