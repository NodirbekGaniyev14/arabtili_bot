"""Dars testi / nazorat testi / zaif so'zlar — ball SERVERda, har savol «qulflanadi» (K33.2).

Avval mijoz `correct/total` ni o'zi hisoblab yuborardi (dars XP, darsning o'tilishi — keyingi darsni ochadi,
taklif mukofoti) va savollar to'g'ri javobi bilan kelardi. Endi:

  1. savollar serverda yaratiladi va `QuizRun` da saqlanadi; mijozga JAVOBSIZ beriladi (blind_quiz.public_item);
  2. o'quvchi har savolga javob beradi → `lock_answer`: server baholaydi, javobni QULFLAYDI (qayta o'zgartirib
     bo'lmaydi) va faqat shundan keyin to'g'ri javob + izohni qaytaradi — darsdagi darhol feedback saqlanadi;
  3. dars «tugatilganda» mijoz faqat `run_id` yuboradi; ball qulflangan javoblardan hisoblanadi
     (javobsiz qolgan savol = xato).

Qolgan zaiflik (ongli): to'g'ri javob qulflangach ochiladi — skript bir urinishda bilib olib, ikkinchisida
yozishi mumkin. Shuning uchun: darsda har urinishda savollar variantli (lesson_test), urinishlar soatiga
cheklangan (MAX_RUNS_PER_HOUR) va XP kunlik chegarada qoladi (xp_guard).
"""

from __future__ import annotations

import json
from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import QuizRun, utcnow
from services import answer_log, blind_quiz

MAX_RUNS_PER_HOUR = 40  # bir o'quvchi soatiga shuncha urinish boshlay oladi (halol o'quvchi 5–10 ta)
REUSE_MINUTES = 30  # hali birorta javob berilmagan urinish yangilanganda (refresh) qayta ishlatiladi
KEEP_DAYS = 14


class TooManyRuns(Exception):
    """Soatiga urinish chegarasi."""


def _log_context(run: QuizRun) -> str:
    return {"lesson": run.ref, "lcp": f"{run.ref}:cp"}.get(run.kind, run.kind)[:24]


async def abandoned_count(session: AsyncSession, user_id: int, kind: str, ref: str) -> int:
    """Birorta javob berilgan, lekin tugatilmagan urinishlar — keyingi urinishda boshqa savollar chiqishi uchun."""
    return int(
        (
            await session.execute(
                select(func.count(QuizRun.id)).where(
                    QuizRun.user_id == user_id,
                    QuizRun.kind == kind,
                    QuizRun.ref == ref,
                    QuizRun.finished_at.is_(None),
                    QuizRun.answers_json != "{}",
                )
            )
        ).scalar_one()
    )


async def create_run(
    session: AsyncSession,
    user_id: int,
    kind: str,
    ref: str,
    items: list[dict],
    extra: dict | None = None,
) -> QuizRun:
    """Yangi urinish (yoki yaqinda boshlangan, hali javobsiz urinish). `extra` — mijozga kerak bo'lgan
    qo'shimcha ma'lumot (masalan, o'qish matni savollarining boshlanish indeksi)."""
    now = utcnow()
    await session.execute(delete(QuizRun).where(QuizRun.created_at < now - timedelta(days=KEEP_DAYS)))

    fresh = (
        await session.execute(
            select(QuizRun)
            .where(
                QuizRun.user_id == user_id,
                QuizRun.kind == kind,
                QuizRun.ref == ref,
                QuizRun.finished_at.is_(None),
                QuizRun.answers_json == "{}",
                QuizRun.created_at > now - timedelta(minutes=REUSE_MINUTES),
            )
            .order_by(QuizRun.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if fresh is not None:
        return fresh

    started = (
        await session.execute(
            select(func.count(QuizRun.id)).where(
                QuizRun.user_id == user_id, QuizRun.created_at > now - timedelta(hours=1)
            )
        )
    ).scalar_one()
    if started >= MAX_RUNS_PER_HOUR:
        raise TooManyRuns()

    run = QuizRun(
        user_id=user_id,
        kind=kind,
        ref=ref,
        items_json=json.dumps({"items": items, "extra": extra or {}}, ensure_ascii=False),
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


def items_of(run: QuizRun) -> list[dict]:
    return json.loads(run.items_json)["items"]


def extra_of(run: QuizRun) -> dict:
    return json.loads(run.items_json).get("extra") or {}


async def get_run(session: AsyncSession, user_id: int, run_id: int, kind: str | None = None, ref: str | None = None):
    """Foydalanuvchining TUGATILMAGAN urinishi (boshqa odamniki yoki tugatilgani — None)."""
    q = select(QuizRun).where(QuizRun.id == run_id, QuizRun.user_id == user_id, QuizRun.finished_at.is_(None))
    if kind is not None:
        q = q.where(QuizRun.kind == kind)
    if ref is not None:
        q = q.where(QuizRun.ref == ref)
    return (await session.execute(q)).scalar_one_or_none()


def reveal(item: dict, index: int, rec: dict) -> dict:
    """Javob qulflangach ko'rsatiladigan ma'lumot: to'g'ri javob, izoh, xato variant izohi."""
    ok = bool(rec["ok"])
    given = rec["g"]
    return {
        "index": index,
        "ok": ok,
        "given": given,
        "answer": item.get("answer", ""),
        "accept": list(item.get("accept") or []),
        "explain_uz": item.get("explain_uz") or "",
        "note": "" if ok else (item.get("option_notes") or {}).get(given, ""),
    }


async def lock_answer(session: AsyncSession, run: QuizRun, index: int, given: str) -> dict | None:
    """Savolga javobni baholaydi va QULFLAYDI. Allaqachon javob berilgan bo'lsa — avvalgisi qaytadi (o'zgarmaydi).
    `index` chegaradan tashqarida bo'lsa None."""
    items = items_of(run)
    if not 0 <= index < len(items):
        return None
    answers = json.loads(run.answers_json)
    key = str(index)
    item = items[index]
    if key not in answers:
        given = (given or "")[:300]
        ok = blind_quiz.check_item(item, given)
        answers[key] = {"g": given, "ok": int(ok)}
        run.answers_json = json.dumps(answers, ensure_ascii=False)
        session.add(run)
        if not ok and given.strip() and blind_quiz.input_kind(item) in ("ar", "lat", "harakat"):
            # rad etilgan yozma javoblar admin /javoblar ga (avval mijoz api.logWrongAnswer bilan yozardi)
            await answer_log.record(
                session, run.user_id, _log_context(run), item.get("type", ""),
                item.get("q_uz") or item.get("q_ar") or "", item.get("answer", ""), given,
            )
        await session.commit()
    return reveal(item, index, answers[key])


def summarize(run: QuizRun) -> dict:
    """Qulflangan javoblardan natija. Javobsiz qolgan savol — xato (ball), lekin SRS'ga tushmaydi."""
    items = items_of(run)
    answers = json.loads(run.answers_json)
    correct = sum(1 for i in range(len(items)) if answers.get(str(i), {}).get("ok"))
    wrong_words = []
    for i, item in enumerate(items):
        rec = answers.get(str(i))
        if rec is not None and not rec["ok"]:
            w = blind_quiz._wrong_word(item)
            if w:
                wrong_words.append(w)
    return {"correct": correct, "total": len(items), "wrong_words": wrong_words}


async def finish(session: AsyncSession, run: QuizRun) -> dict:
    """Urinishni yopadi (qayta hisoblab bo'lmaydi) va natijani qaytaradi. Commit chaqiruvchida."""
    result = summarize(run)
    run.finished_at = utcnow()
    session.add(run)
    return result
