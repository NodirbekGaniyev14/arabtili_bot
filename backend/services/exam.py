"""Imtihon dvigateli (spec §12): tasodifiy savollar, 4 bo'lim, 80/60 qoidasi,
24 soat qayta topshirish qulfi."""

import json
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import BASE_DIR
from db.models import ExamAttempt, Progress
from services.curriculum import load_curriculum, written_lesson_ids
from services.qbank import pick_fresh, qhash

EXAMS_DIR = BASE_DIR / "content" / "exams"
COOLDOWN_HOURS = 24
PASS_TOTAL = 80  # yakuniy 80%+ yetarli (bo'lim bo'yicha minimal talab yo'q)
GRACE_MINUTES = 3

LEVEL_ORDER = ["A0", "A1", "A2", "B1", "B2"]
UNLOCK_RATIO = 0.8  # daraja darslarining 80% tugagach imtihon ochiladi


def next_level(level: str) -> str | None:
    """Keyingi daraja (oxirgisidan keyin — None)."""
    if level not in LEVEL_ORDER:
        return None
    i = LEVEL_ORDER.index(level)
    return LEVEL_ORDER[i + 1] if i + 1 < len(LEVEL_ORDER) else None


def level_lesson_ids(level: str) -> set[str]:
    """Shu darajadagi YOZILGAN darslar (imtihon tugunlari hisobga olinmaydi)."""
    written = written_lesson_ids()
    return {
        lid
        for lid, meta in load_curriculum().items()
        if meta["level"] == level and meta["type"] == "lesson" and lid in written
    }


async def level_progress(
    session: AsyncSession, user_id: int, level: str
) -> tuple[int, int]:
    """(tugatilgan, jami) — shu darajadagi darslar bo'yicha."""
    ids = level_lesson_ids(level)
    if not ids:
        return 0, 0
    done_rows = (
        await session.execute(
            select(Progress.lesson_id)
            .where(Progress.user_id == user_id, Progress.passed == 1)
            .distinct()
        )
    ).scalars().all()
    return len(ids & set(done_rows)), len(ids)


def unlock_threshold(total: int) -> int:
    """Imtihon ochilishi uchun kerakli dars soni (80%, kamida 1 ta)."""
    return max(1, -(-total * 8 // 10)) if total else 0  # yuqoriga yaxlitlash


async def backfill_levels(session: AsyncSession) -> int:
    """Ilgari imtihondan o'tgan, ammo darajasi ko'tarilmagan foydalanuvchilar.

    Daraja o'sishi K10'da qo'shildi — undan oldin imtihondan o'tganlar eski
    darajada qolib ketgan edi. Ishga tushishda bir marta to'g'rilaymiz.
    """
    from db.models import Plan  # aylanma importdan qochish

    plans = (await session.execute(select(Plan))).scalars().all()
    if not plans:
        return 0

    passed_rows = (
        await session.execute(
            select(ExamAttempt.user_id, ExamAttempt.level).where(
                ExamAttempt.passed == 1, ExamAttempt.kind == "level"
            )
        )
    ).all()
    passed: dict[int, set[str]] = {}
    for uid, lvl in passed_rows:
        passed.setdefault(uid, set()).add(lvl)

    fixed = 0
    for plan in plans:
        mine = passed.get(plan.user_id)
        if not mine:
            continue
        # Joriy darajadan boshlab, o'tilgan imtihonlar zanjiri bo'yicha ko'taramiz
        level = plan.level
        while level in mine:
            nxt = next_level(level)
            if not nxt:
                break
            level = nxt
        if level != plan.level:
            plan.level = level
            session.add(plan)
            fixed += 1

    if fixed:
        await session.commit()
    return fixed


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def load_pool(level: str) -> dict | None:
    f = EXAMS_DIR / f"{level.lower()}_pool.json"
    if not f.exists():
        return None
    return json.loads(f.read_text(encoding="utf-8"))


def exam_available(level: str) -> bool:
    return load_pool(level) is not None


async def cooldown_until(
    session: AsyncSession, user_id: int, level: str
) -> datetime | None:
    """Oxirgi yiqilgan urinishdan 24 soat o'tmagan bo'lsa — qulf tugash vaqti."""
    last = (
        await session.execute(
            select(ExamAttempt)
            .where(
                ExamAttempt.user_id == user_id,
                ExamAttempt.level == level,
                ExamAttempt.kind == "level",
                ExamAttempt.finished_at.isnot(None),
            )
            .order_by(ExamAttempt.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if last and not last.passed and last.finished_at:
        until = last.finished_at + timedelta(hours=COOLDOWN_HOURS)
        if until > _now():
            return until
    return None


async def already_passed(
    session: AsyncSession, user_id: int, level: str
) -> bool:
    row = (
        await session.execute(
            select(ExamAttempt.id).where(
                ExamAttempt.user_id == user_id,
                ExamAttempt.level == level,
                ExamAttempt.kind == "level",
                ExamAttempt.passed == 1,
            ).limit(1)
        )
    ).scalar_one_or_none()
    return row is not None


async def seen_questions(
    session: AsyncSession, user_id: int, level: str
) -> set[str]:
    """Foydalanuvchi shu daraja imtihonida ILGARI KO'RGAN savollar xeshi.

    Yiqilgandan keyin 24 soat o'tib qayta topshirilganda AYNAN o'sha test
    tushmasligi kerak (foydalanuvchi talabi) — shuning uchun oldingi
    urinishlardagi savollar chetlab o'tiladi.
    """
    rows = (
        await session.execute(
            select(ExamAttempt.questions_json).where(
                ExamAttempt.user_id == user_id,
                ExamAttempt.level == level,
                ExamAttempt.kind == "level",
            )
        )
    ).scalars().all()

    seen: set[str] = set()
    for raw in rows:
        try:
            data = json.loads(raw or "{}")
        except ValueError:
            continue
        for section in ("reading", "listening", "writing", "speaking", "passages"):
            for item in data.get(section) or []:
                if isinstance(item, dict):
                    seen.add(qhash(item))
    return seen


def build_exam(level: str, seen: set[str] | None = None) -> dict | None:
    """Pooldan imtihon yig'adi — imkon qadar KO'RILMAGAN savollardan."""
    pool = load_pool(level)
    if not pool:
        return None
    cfg = pool["config"]
    rnd = random.Random()

    def sample(items: list, n: int) -> list:
        return pick_fresh(list(items), n, seen, rnd)

    return {
        "level": level,
        "minutes": cfg["minutes"],
        "reading": sample(pool["reading"], cfg["reading"]),
        "listening": sample(pool["listening"], cfg["listening"]),
        "writing": sample(pool["writing"], cfg["writing"]),
        # 4-bo'lim: A0/A1 da gapirish, A2 va yuqorida matn o'qish (passages)
        "speaking": sample(pool.get("speaking", []), cfg.get("speaking", 0)),
        "passages": sample(pool.get("passages", []), cfg.get("passages", 0)),
    }


def passage_questions(exam: dict) -> int:
    """Matn bo'limidagi savollar soni."""
    return sum(len(p.get("questions", [])) for p in exam.get("passages") or [])


async def start_attempt(
    session: AsyncSession, user_id: int, level: str, exam: dict
) -> ExamAttempt:
    attempt = ExamAttempt(
        user_id=user_id,
        level=level,
        questions_json=json.dumps(exam, ensure_ascii=False),
    )
    session.add(attempt)
    await session.commit()
    await session.refresh(attempt)
    return attempt


def grade(
    attempt: ExamAttempt,
    reading_correct: int,
    listening_correct: int,
    writing_score: int,
    speaking_score: int,
    passage_correct: int = 0,
) -> dict:
    """Bo'lim ballari (0-100) va yakuniy natija.

    4-bo'lim darajaga qarab o'zgaradi: A0/A1 da gapirish, A2 va yuqorida
    matn o'qish. Ball baribir `speaking` kalitida qaytadi (DB ustuni o'sha),
    `fourth` esa qaysi bo'lim ekanini bildiradi.
    """
    exam = json.loads(attempt.questions_json)
    n_r = max(1, len(exam["reading"]))
    n_l = max(1, len(exam["listening"]))

    s_reading = round(100 * min(reading_correct, n_r) / n_r)
    s_listening = round(100 * min(listening_correct, n_l) / n_l)
    s_writing = max(0, min(100, writing_score))

    n_p = passage_questions(exam)
    if n_p:
        fourth = "passage"
        s_speaking = round(100 * min(max(0, passage_correct), n_p) / n_p)
    else:
        fourth = "speaking"
        s_speaking = max(0, min(100, speaking_score))

    total = round((s_reading + s_listening + s_writing + s_speaking) / 4)
    passed = total >= PASS_TOTAL  # umumiy 80%+ — bo'lim minimumi olib tashlandi

    # Vaqt chegarasi (server tomonda ham)
    limit = exam.get("minutes", 30) + GRACE_MINUTES
    elapsed_min = (_now() - attempt.started_at).total_seconds() / 60
    timed_out = elapsed_min > limit
    if timed_out:
        passed = False

    return {
        "reading": s_reading,
        "listening": s_listening,
        "writing": s_writing,
        "speaking": s_speaking,
        "fourth": fourth,
        "total": total,
        "passed": passed,
        "timed_out": timed_out,
    }
