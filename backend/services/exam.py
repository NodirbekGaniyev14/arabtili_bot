"""Imtihon dvigateli (spec §12): tasodifiy savollar, 4 bo'lim, 80/60 qoidasi,
24 soat qayta topshirish qulfi."""

import json
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import BASE_DIR
from db.models import ExamAttempt

EXAMS_DIR = BASE_DIR / "content" / "exams"
COOLDOWN_HOURS = 24
PASS_TOTAL = 80
PASS_SECTION = 60
GRACE_MINUTES = 3


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
                ExamAttempt.passed == 1,
            ).limit(1)
        )
    ).scalar_one_or_none()
    return row is not None


def build_exam(level: str) -> dict | None:
    """Pooldan tasodifiy imtihon yig'adi."""
    pool = load_pool(level)
    if not pool:
        return None
    cfg = pool["config"]

    def sample(items: list, n: int) -> list:
        items = list(items)
        random.shuffle(items)
        return items[: min(n, len(items))]

    return {
        "level": level,
        "minutes": cfg["minutes"],
        "reading": sample(pool["reading"], cfg["reading"]),
        "listening": sample(pool["listening"], cfg["listening"]),
        "writing": sample(pool["writing"], cfg["writing"]),
        "speaking": sample(pool["speaking"], cfg["speaking"]),
    }


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
) -> dict:
    """Bo'lim ballari (0-100) va yakuniy natija."""
    exam = json.loads(attempt.questions_json)
    n_r = max(1, len(exam["reading"]))
    n_l = max(1, len(exam["listening"]))

    s_reading = round(100 * min(reading_correct, n_r) / n_r)
    s_listening = round(100 * min(listening_correct, n_l) / n_l)
    s_writing = max(0, min(100, writing_score))
    s_speaking = max(0, min(100, speaking_score))

    total = round((s_reading + s_listening + s_writing + s_speaking) / 4)
    passed = total >= PASS_TOTAL and all(
        s >= PASS_SECTION for s in (s_reading, s_listening, s_writing, s_speaking)
    )

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
        "total": total,
        "passed": passed,
        "timed_out": timed_out,
    }
