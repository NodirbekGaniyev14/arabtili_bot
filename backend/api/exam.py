"""Imtihon + sertifikat API (K3)."""

import html
import json
import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Certificate, ExamAttempt, Plan, Progress, User, XpLog
from db.session import get_session
from services import answer_log, blind_quiz
from services import challenge as challenge_svc
from services import checkpoint as checkpoint_svc
from services import exam as exam_svc
from services.certificate import issue_certificate
from services.telegram_auth import get_current_user

router = APIRouter()

PASS_XP = 50
MINI_PASS_XP = 15  # mini-imtihondan o'tgani uchun


async def _user_level(session: AsyncSession, user_id: int) -> str:
    plan = (
        await session.execute(
            select(Plan).where(Plan.user_id == user_id).order_by(Plan.id.desc()).limit(1)
        )
    ).scalar_one_or_none()
    return plan.level if plan else "A0"


async def _level_exam_state(session: AsyncSession, user_id: int, level: str, user_level: str) -> dict:
    """Bitta daraja imtihonining holati."""
    available = exam_svc.exam_available(level)
    cooldown = await exam_svc.cooldown_until(session, user_id, level)
    passed = await exam_svc.already_passed(session, user_id, level)
    pool = exam_svc.load_pool(level) if available else None

    done, total = await exam_svc.level_progress(session, user_id, level)
    needed = exam_svc.unlock_threshold(total)

    # Foydalanuvchi darajasidan PAST darajalar har doim ochiq — o'sha bosqichdan
    # o'tib kelgan (yoki daraja testi shunday aniqlagan), qayta topshira oladi.
    below_current = exam_svc.LEVEL_ORDER.index(level) < exam_svc.LEVEL_ORDER.index(
        user_level
    ) if level in exam_svc.LEVEL_ORDER and user_level in exam_svc.LEVEL_ORDER else False
    # Yuqori darajalar — reja darajasidan oshib ketolmaydi
    above_current = exam_svc.LEVEL_ORDER.index(level) > exam_svc.LEVEL_ORDER.index(
        user_level
    ) if level in exam_svc.LEVEL_ORDER and user_level in exam_svc.LEVEL_ORDER else False

    unlocked = (not above_current) and (below_current or passed or done >= needed)

    return {
        "level": level,
        "available": available,
        "already_passed": passed,
        "cooldown_until": cooldown.isoformat() if cooldown else None,
        "minutes": pool["config"]["minutes"] if pool else 0,
        "counts": pool["config"] if pool else {},
        "unlocked": unlocked,
        "locked_reason": (
            "above" if above_current else ("lessons" if not unlocked else "")
        ),
        "lessons_done": done,
        "lessons_total": total,
        "lessons_needed": needed,
        "percent": round(done / total * 100) if total else 0,
    }


@router.get("/api/exam/info")
async def exam_info(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Barcha darajalar imtihoni holati + joriy daraja."""
    user_level = await _user_level(session, user.id)
    levels = [
        await _level_exam_state(session, user.id, lvl, user_level)
        for lvl in exam_svc.LEVEL_ORDER
    ]
    current = next((x for x in levels if x["level"] == user_level), levels[0])

    return {
        # Joriy daraja holati — eski mijozlar uchun ham to'g'ri ishlaydi
        **current,
        "user_level": user_level,
        "levels": levels,
        "next_level": exam_svc.next_level(user_level),
    }


STALE_CLIENT = (
    "Ilova yangilangan — Telegram'ni yopib qayta oching, so'ng imtihonni boshidan boshlang"
)


@router.post("/api/exam/start")
async def exam_start(
    level: str = "",
    v: int = 1,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    # K33: v=2 — javobsiz savollar, ball serverda. Eski (keshlangan) mijoz javobni o'zi tekshiradi va ball
    # raqamini yuboradi — u endi ishlamaydi; jim noto'g'ri natija o'rniga aniq xabar.
    if v < 2:
        raise HTTPException(status_code=426, detail=STALE_CLIENT)
    user_level = await _user_level(session, user.id)
    level = (level or user_level).upper()
    if level not in exam_svc.LEVEL_ORDER:
        raise HTTPException(status_code=400, detail="Noma'lum daraja")

    if not exam_svc.exam_available(level):
        raise HTTPException(status_code=404, detail="Bu daraja uchun imtihon hali yo'q")

    state = await _level_exam_state(session, user.id, level, user_level)
    if not state["unlocked"]:
        if state["locked_reason"] == "above":
            raise HTTPException(
                status_code=403,
                detail=f"{level} imtihoni hali ochilmagan — avval {user_level} ni tugating",
            )
        raise HTTPException(
            status_code=403,
            detail=(
                f"Imtihon uchun {state['lessons_needed']} ta dars kerak — "
                f"hozir {state['lessons_done']} ta tugatilgan"
            ),
        )

    cooldown = await exam_svc.cooldown_until(session, user.id, level)
    if cooldown:
        raise HTTPException(
            status_code=429,
            detail=f"Qayta topshirish: {cooldown.isoformat()} dan keyin",
        )
    # Qayta topshirishda oldingi urinishlar savollari chetlab o'tiladi
    seen = await exam_svc.seen_questions(session, user.id, level)
    exam = exam_svc.build_exam(level, seen)
    attempt = await exam_svc.start_attempt(session, user.id, level, exam)
    # To'liq nusxa (javoblar bilan) faqat bazada; mijozga — javobsiz
    return {"attempt_id": attempt.id, **exam_svc.public_exam(exam)}


Answer = Annotated[str, StringConstraints(max_length=300)]
WrittenText = Annotated[str, StringConstraints(max_length=4000)]


class SubmitBody(BaseModel):
    """K33: mijoz BALL emas, TANLAGAN javoblarni yuboradi — savollar tartibida; "" = javob berilmagan."""

    attempt_id: int
    reading: list[Answer] | None = Field(default=None, max_length=100)
    listening: list[Answer] | None = Field(default=None, max_length=100)
    # A2+: matn bo'limi — har matn uchun o'z javoblar ro'yxati
    passages: list[list[Answer]] | None = Field(default=None, max_length=30)
    writing: list[WrittenText] | None = Field(default=None, max_length=30)
    # A0/A1: «✓ Aytdim» bosilgan soni (ovoz yozilmaydi)
    speaking_done: int = Field(default=0, ge=0, le=100)
    holder_name: str = Field(default="", max_length=100)


@router.post("/api/exam/submit")
async def exam_submit(
    body: SubmitBody,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    attempt = (
        await session.execute(
            select(ExamAttempt).where(
                ExamAttempt.id == body.attempt_id,
                ExamAttempt.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if attempt is None:
        raise HTTPException(status_code=404, detail="Urinish topilmadi")
    if attempt.finished_at is not None:
        raise HTTPException(status_code=409, detail="Bu urinish yakunlangan")
    if body.reading is None or body.listening is None:
        # Eski mijoz (ball raqamlarini yuboradi) — urinish YAKUNLANMAYDI: o'quvchi qayta boshlay oladi, 24 soat qulfsiz
        raise HTTPException(status_code=426, detail=STALE_CLIENT)

    exam = json.loads(attempt.questions_json)
    counts = exam_svc.grade_answers(
        exam, body.reading, body.listening, body.passages, body.writing, body.speaking_done
    )
    result = exam_svc.grade(
        attempt,
        counts["reading_correct"],
        counts["listening_correct"],
        counts["writing_score"],
        counts["speaking_score"],
        counts["passage_correct"],
    )

    # Rad etilgan diktant javoblari admin /javoblar ga tushadi (avval QuizRunner mijoz tomonda yozardi)
    given = list(body.listening)
    for i, item in enumerate(exam.get("listening") or []):
        if item.get("type") == "dictation" and i < len(given) and not exam_svc.check_item(item, given[i]):
            await answer_log.record(
                session, user.id, "exam:listening", "dictation",
                item.get("q_uz", ""), item["answer"], given[i],
            )

    attempt.finished_at = exam_svc._now()
    attempt.score_reading = result["reading"]
    attempt.score_listening = result["listening"]
    attempt.score_writing = result["writing"]
    attempt.score_speaking = result["speaking"]
    attempt.total_score = result["total"]
    attempt.passed = 1 if result["passed"] else 0
    session.add(attempt)

    cert_data = None
    promoted_to = None
    if result["passed"]:
        session.add(
            XpLog(user_id=user.id, amount=PASS_XP, source=f"exam:{attempt.level}")
        )

        # Daraja ko'tarilishi — faqat joriy darajadan yuqoriga
        plan = (
            await session.execute(
                select(Plan).where(Plan.user_id == user.id).order_by(Plan.id.desc()).limit(1)
            )
        ).scalar_one_or_none()
        nxt = exam_svc.next_level(attempt.level)
        # Kontenti hali yozilmagan darajaga ko'tarmaymiz (masalan B2 tayyor
        # bo'lmaganda) — aks holda foydalanuvchi bo'sh darajaga tushib qoladi.
        if nxt and not exam_svc.level_lesson_ids(nxt):
            nxt = None
        if plan and nxt and plan.level == attempt.level:
            plan.level = nxt
            session.add(plan)
            promoted_to = nxt

        await session.commit()

        holder = body.holder_name.strip() or user.name
        cert = await issue_certificate(
            session, user.id, holder, attempt.level, result["total"],
            {
                k: result[k]
                for k in ("reading", "listening", "writing", "speaking", "fourth")
            },
        )
        cert_data = {
            "cert_id": cert.cert_id,
            "png_url": f"/api/certificates/{cert.cert_id}.png",
            "verify_code": cert.cert_id.split("-")[-1],
        }
        # Botga yuborish (server rejimida)
        bot = getattr(request.app.state, "bot", None)
        if bot:
            try:
                from aiogram.types import (
                    FSInputFile,
                    InlineKeyboardButton,
                    InlineKeyboardMarkup,
                )
                from urllib.parse import quote

                share_text = quote(
                    f"Men Arabiy'da {attempt.level} kursini tugatdim! 🎓"
                )
                share_url = quote("https://t.me/JamalArabiy_bot")
                kb = InlineKeyboardMarkup(
                    inline_keyboard=[[
                        InlineKeyboardButton(
                            text="👥 Do'stlarga ulashish",
                            url=f"https://t.me/share/url?url={share_url}&text={share_text}",
                        )
                    ]]
                )
                await bot.send_photo(
                    user.tg_id,
                    FSInputFile(cert.png_path),
                    caption=(
                        f"🏅 Tabriklaymiz! {attempt.level} kursini tugatganlik "
                        f"sertifikati — yakuniy imtihon {result['total']}/100"
                    ),
                    reply_markup=kb,
                )
                if cert.pdf_path:
                    await bot.send_document(user.tg_id, FSInputFile(cert.pdf_path))
                if promoted_to:
                    await bot.send_message(
                        user.tg_id,
                        f"🎉 <b>{promoted_to} darajasi ochildi!</b>\n\n"
                        f"{attempt.level} imtihonidan o'tdingiz — endi darslar "
                        f"{promoted_to} darajasidan davom etadi. Omad!",
                        parse_mode="HTML",
                    )
            except Exception:
                pass
    else:
        await session.commit()

    return {
        **result,
        "xp_earned": PASS_XP if result["passed"] else 0,
        "certificate": cert_data,
        "promoted_to": promoted_to,
    }


# ─────────────────── Mini-imtihonlar (25% / 50% / 75%) ───────────────────


@router.get("/api/checkpoint/info")
async def checkpoint_info(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Daraja bo'yicha mini-imtihonlar holati."""
    level = await _user_level(session, user.id)
    done, total = await exam_svc.level_progress(session, user.id, level)

    passed_rows = (
        await session.execute(
            select(ExamAttempt.checkpoint, ExamAttempt.total_score, ExamAttempt.passed)
            .where(
                ExamAttempt.user_id == user.id,
                ExamAttempt.level == level,
                ExamAttempt.kind == "mini",
                ExamAttempt.finished_at.isnot(None),
            )
            .order_by(ExamAttempt.id)
        )
    ).all()
    best: dict[int, dict] = {}
    for cp, score, ok in passed_rows:
        cur = best.get(cp)
        if cur is None or score > cur["score"]:
            best[cp] = {"score": score, "passed": bool(ok)}

    items = []
    for cp in checkpoint_svc.checkpoints_for(level):
        rec = best.get(cp["percent"])
        items.append(
            {
                "percent": cp["percent"],
                "need": cp["need"],
                "unlocked": done >= cp["need"],
                "attempted": rec is not None,
                "passed": bool(rec and rec["passed"]),
                "best_score": rec["score"] if rec else None,
            }
        )

    # Hozir topshirish mumkin bo'lgan birinchi mini-imtihon (o'tilmagani)
    due = next(
        (i["percent"] for i in items if i["unlocked"] and not i["passed"]), None
    )
    return {
        "level": level,
        "lessons_done": done,
        "lessons_total": total,
        "pass_score": checkpoint_svc.PASS,
        "checkpoints": items,
        "due": due,
    }


@router.post("/api/checkpoint/start")
async def checkpoint_start(
    percent: int,
    v: int = 1,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if v < 2:  # K33: javobsiz savollar, ball serverda — eski keshlangan mijoz ishlamaydi
        raise HTTPException(status_code=426, detail=STALE_CLIENT)
    level = await _user_level(session, user.id)
    cp = next(
        (c for c in checkpoint_svc.checkpoints_for(level) if c["percent"] == percent),
        None,
    )
    if cp is None:
        raise HTTPException(status_code=404, detail="Bunday mini-imtihon yo'q")

    done, _ = await exam_svc.level_progress(session, user.id, level)
    if done < cp["need"]:
        raise HTTPException(
            status_code=403,
            detail=f"Mini-imtihon uchun {cp['need']} ta dars kerak — hozir {done} ta",
        )

    # Oldingi urinishlarda tushgan savollarni chetlab o'tamiz
    from services.qbank import qhash

    prev = (
        await session.execute(
            select(ExamAttempt.questions_json).where(
                ExamAttempt.user_id == user.id,
                ExamAttempt.level == level,
                ExamAttempt.kind == "mini",
                ExamAttempt.checkpoint == percent,
            )
        )
    ).scalars().all()
    seen: set[str] = set()
    for raw in prev:
        try:
            for it in json.loads(raw or "{}").get("items") or []:
                if isinstance(it, dict):
                    seen.add(qhash(it))
        except ValueError:
            continue

    mini = checkpoint_svc.build_mini(level, percent, seen_hashes=seen)
    if not mini:
        raise HTTPException(status_code=404, detail="Savol banki bo'sh")

    attempt = ExamAttempt(
        user_id=user.id,
        level=level,
        kind="mini",
        checkpoint=percent,
        questions_json=json.dumps(mini, ensure_ascii=False),
    )
    session.add(attempt)
    await session.commit()
    await session.refresh(attempt)
    # To'liq nusxa (javoblar bilan) faqat bazada; mijozga — javobsiz
    return {
        "attempt_id": attempt.id,
        "level": mini["level"],
        "percent": mini["percent"],
        "lessons_covered": mini["lessons_covered"],
        "pass_score": mini["pass_score"],
        "items": blind_quiz.public_items(mini["items"]),
    }


class CheckpointSubmit(BaseModel):
    """K33: mijoz BALL emas, o'quvchi javoblarini yuboradi — savollar tartibida; "" = javob berilmagan."""

    attempt_id: int
    answers: list[Answer] | None = Field(default=None, max_length=60)


async def _log_rejected(session: AsyncSession, user_id: int, context: str, graded: blind_quiz.GradeResult) -> None:
    """Rad etilgan yozma javoblar admin /javoblar ga tushadi (avval QuizRunner mijoz tomonda yozardi)."""
    for item, given in graded.rejected:
        await answer_log.record(
            session, user_id, context, item.get("type", ""), item.get("q_uz") or item.get("q_ar") or "",
            item["answer"], given,
        )


@router.post("/api/checkpoint/submit")
async def checkpoint_submit(
    body: CheckpointSubmit,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    attempt = (
        await session.execute(
            select(ExamAttempt).where(
                ExamAttempt.id == body.attempt_id,
                ExamAttempt.user_id == user.id,
                ExamAttempt.kind == "mini",
            )
        )
    ).scalar_one_or_none()
    if attempt is None:
        raise HTTPException(status_code=404, detail="Urinish topilmadi")
    if attempt.finished_at is not None:
        raise HTTPException(status_code=409, detail="Bu urinish yakunlangan")
    if body.answers is None:
        # Eski mijoz (correct/total yuboradi) — urinish YAKUNLANMAYDI, o'quvchi qayta boshlay oladi
        raise HTTPException(status_code=426, detail=STALE_CLIENT)

    items = json.loads(attempt.questions_json).get("items") or []
    graded = blind_quiz.grade_items(items, body.answers)
    result = checkpoint_svc.grade(graded.correct, graded.total)
    await _log_rejected(session, user.id, f"cp{attempt.checkpoint}", graded)

    # XP — har (daraja, mini-imtihon) uchun BIR marta (avval har o'tishda berilardi: qayta-qayta topshirib «ekish» mumkin edi)
    already_paid = (
        await session.execute(
            select(ExamAttempt.id)
            .where(
                ExamAttempt.user_id == user.id,
                ExamAttempt.level == attempt.level,
                ExamAttempt.kind == "mini",
                ExamAttempt.checkpoint == attempt.checkpoint,
                ExamAttempt.passed == 1,
                ExamAttempt.id != attempt.id,
            )
            .limit(1)
        )
    ).scalar_one_or_none() is not None

    attempt.finished_at = exam_svc._now()
    attempt.total_score = result["score"]
    attempt.passed = 1 if result["passed"] else 0
    session.add(attempt)

    xp = MINI_PASS_XP if (result["passed"] and not already_paid) else 0
    if xp:
        session.add(
            XpLog(
                user_id=user.id,
                amount=xp,
                source=f"checkpoint:{attempt.level}:{attempt.checkpoint}",
            )
        )
    await session.commit()

    # Xato so'zlar takrorga qaytadi (qulf yo'q — faqat mustahkamlash)
    from services.srs import reset_words

    reset_n = await reset_words(session, user.id, graded.wrong_words)

    return {
        **result,
        "level": attempt.level,
        "percent": attempt.checkpoint,
        "xp_earned": xp,
        "xp_already_claimed": result["passed"] and already_paid,
        "srs_reset": reset_n,
        "locked": False,
        "review": graded.review,
    }


# ──────────────────────── Haftalik chellenj ────────────────────────


async def _done_lessons(session: AsyncSession, user_id: int) -> list[str]:
    """Foydalanuvchi tugatgan darslar — kurikulum tartibida."""
    from services.curriculum import lesson_order

    rows = (
        await session.execute(
            select(Progress.lesson_id)
            .where(Progress.user_id == user_id, Progress.passed == 1)
            .distinct()
        )
    ).scalars().all()
    done = set(rows)
    return [lid for lid in lesson_order() if lid in done]


async def _week_attempt(session: AsyncSession, user_id: int) -> ExamAttempt | None:
    return (
        await session.execute(
            select(ExamAttempt)
            .where(
                ExamAttempt.user_id == user_id,
                ExamAttempt.kind == "weekly",
                ExamAttempt.checkpoint == challenge_svc.week_key(),
                ExamAttempt.finished_at.isnot(None),
            )
            .order_by(ExamAttempt.total_score.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


@router.get("/api/challenge/info")
async def challenge_info(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    lessons = await _done_lessons(session, user.id)
    best = await _week_attempt(session, user.id)
    return {
        "week": challenge_svc.week_key(),
        "week_label": challenge_svc.week_label(),
        "available": len(lessons) > 0,
        "lessons_pool": len(lessons),
        "questions": challenge_svc.N_QUESTIONS,
        "pass_score": challenge_svc.PASS,
        "xp_reward": challenge_svc.XP_REWARD,
        "attempted": best is not None,
        "passed": bool(best and best.passed),
        "best_score": best.total_score if best else None,
    }


@router.post("/api/challenge/start")
async def challenge_start(
    v: int = 1,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if v < 2:  # K33: javobsiz savollar, ball serverda — eski keshlangan mijoz ishlamaydi
        raise HTTPException(status_code=426, detail=STALE_CLIENT)
    lessons = await _done_lessons(session, user.id)
    data = challenge_svc.build_challenge(lessons, user.id)
    if not data:
        raise HTTPException(
            status_code=404,
            detail="Avval kamida bitta darsni tugating — chellenj shu darslardan tuziladi",
        )

    attempt = ExamAttempt(
        user_id=user.id,
        level=await _user_level(session, user.id),
        kind="weekly",
        checkpoint=data["week"],
        questions_json=json.dumps(data, ensure_ascii=False),
    )
    session.add(attempt)
    await session.commit()
    await session.refresh(attempt)
    return {
        "attempt_id": attempt.id,
        "week": data["week"],
        "week_label": data["week_label"],
        "pass_score": data["pass_score"],
        "xp_reward": data["xp_reward"],
        "lessons_pool": data["lessons_pool"],
        "items": blind_quiz.public_items(data["items"]),
    }


class ChallengeSubmit(BaseModel):
    attempt_id: int
    answers: list[Answer] | None = Field(default=None, max_length=60)


@router.post("/api/challenge/submit")
async def challenge_submit(
    body: ChallengeSubmit,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    attempt = (
        await session.execute(
            select(ExamAttempt).where(
                ExamAttempt.id == body.attempt_id,
                ExamAttempt.user_id == user.id,
                ExamAttempt.kind == "weekly",
            )
        )
    ).scalar_one_or_none()
    if attempt is None:
        raise HTTPException(status_code=404, detail="Urinish topilmadi")
    if attempt.finished_at is not None:
        raise HTTPException(status_code=409, detail="Bu urinish yakunlangan")
    if body.answers is None:
        raise HTTPException(status_code=426, detail=STALE_CLIENT)

    # XP shu hafta uchun allaqachon berilganmi?
    already_paid = (
        await session.execute(
            select(ExamAttempt.id).where(
                ExamAttempt.user_id == user.id,
                ExamAttempt.kind == "weekly",
                ExamAttempt.checkpoint == attempt.checkpoint,
                ExamAttempt.passed == 1,
                ExamAttempt.id != attempt.id,
            ).limit(1)
        )
    ).scalar_one_or_none() is not None

    items = json.loads(attempt.questions_json).get("items") or []
    graded = blind_quiz.grade_items(items, body.answers)
    result = challenge_svc.grade(graded.correct, graded.total)
    await _log_rejected(session, user.id, "challenge", graded)

    attempt.finished_at = exam_svc._now()
    attempt.total_score = result["score"]
    attempt.passed = 1 if result["passed"] else 0
    session.add(attempt)

    xp = challenge_svc.XP_REWARD if (result["passed"] and not already_paid) else 0
    if xp:
        session.add(
            XpLog(
                user_id=user.id,
                amount=xp,
                source=f"challenge:{attempt.checkpoint}",
            )
        )
    await session.commit()

    from services.srs import reset_words

    reset_n = await reset_words(session, user.id, graded.wrong_words)

    return {
        **result,
        "week": attempt.checkpoint,
        "xp_earned": xp,
        "xp_already_claimed": already_paid,
        "srs_reset": reset_n,
        "review": graded.review,
    }


@router.get("/api/certificates/{cert_file}")
async def cert_file(cert_file: str):
    """Sertifikat PNG/PDF fayli (o'z havolasini bilgan har kim ochadi)."""
    from services.certificate import CERT_DIR

    path = CERT_DIR / cert_file
    if not path.exists() or ".." in cert_file:
        raise HTTPException(status_code=404)
    return FileResponse(path)


@router.get("/api/my-certificates")
async def my_certs(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    rows = (
        await session.execute(
            select(Certificate)
            .where(Certificate.user_id == user.id, Certificate.revoked == 0)
            .order_by(Certificate.id.desc())
        )
    ).scalars().all()
    return {
        "certificates": [
            {
                "cert_id": c.cert_id,
                "kind": c.kind or "level",
                "level": c.level,
                "score": c.score,
                "issued_at": c.issued_at.strftime("%d.%m.%Y"),
                "png_url": f"/api/certificates/{c.cert_id}.png",
            }
            for c in rows
        ]
    }


_VERIFY_CODE = re.compile(r"[A-Z0-9]{4,12}")


@router.get("/api/verify/{code}")
async def verify(code: str, session: AsyncSession = Depends(get_session)):
    """Ochiq tekshirish sahifasi (authsiz) — QR shu yerga olib keladi.

    K28 pentest: (1) kod faqat harf/raqam — ilgari LIKE'ga to'g'ridan-to'g'ri tushardi: «%» bilan barcha
    sertifikat egalarini sanab chiqish mumkin edi (yoki bir nechta mos kelib 500); (2) sahifadagi har bir
    qiymat HTML-escape — `holder_name` ni o'quvchi o'zi yozadi (<script> — saqlanadigan XSS edi)."""
    code = (code or "").strip().upper()
    cert = None
    if _VERIFY_CODE.fullmatch(code):
        rows = (
            await session.execute(
                select(Certificate).where(
                    Certificate.cert_id.like(f"%-{code}"),
                    Certificate.revoked == 0,
                )
            )
        ).scalars().all()
        cert = next((c for c in rows if c.cert_id.split("-")[-1] == code), None)

    if cert is None:
        return HTMLResponse(
            "<html><body style='font-family:sans-serif;text-align:center;padding:60px'>"
            "<h2>❌ Sertifikat topilmadi</h2></body></html>",
            status_code=404,
        )

    def h(v) -> str:
        return html.escape(str(v))

    scores = json.loads(cert.scores_json or "{}")
    kind = cert.kind or "level"
    if kind in ("weekly", "week", "month"):
        rank = scores.get("rank", cert.level.lstrip("WM") or "—")
        period_uz = "Oylik" if kind == "month" else "Haftalik"
        label = scores.get("label") or scores.get("week", "—")
        body = (
            f'<p style="margin:4px">{period_uz} reyting: <b>{h(rank)}-o\'rin</b></p>'
            f'<p style="margin:4px">{period_uz} XP: <b>{h(cert.score)}</b></p>'
            f'<p style="margin:4px;font-size:13px;color:#8A8071">Davr: {h(label)}</p>'
        )
    elif kind == "mock":
        crit = " · ".join(
            f"{uz} {h(scores.get(k))}"
            for k, uz in (("vocab", "Lug'at"), ("grammar", "Grammatika"), ("content", "Mazmun"), ("pron", "Talaffuz"))
            if (scores.get(k) or -1) >= 0
        )
        body = (
            f'<p style="margin:4px">Speaking mock: <b>{h(scores.get("title", "—"))}</b> · daraja {h(cert.level)}</p>'
            f'<p style="margin:4px">Natija: <b>{h(cert.score)}/100</b></p>'
            f'<p style="margin:4px;font-size:13px;color:#8A8071">{crit}</p>'
        )
    else:
        body = (
            f'<p style="margin:4px">Tugatilgan kurs: <b>{h(cert.level)}</b></p>'
            f'<p style="margin:4px">Yakuniy imtihon: <b>{h(cert.score)}/100</b></p>'
            f'<p style="margin:4px;font-size:13px;color:#8A8071">'
            f'O\'qish {h(scores.get("reading","—"))} · Tinglash {h(scores.get("listening","—"))} · '
            f'Yozish {h(scores.get("writing","—"))} · '
            f'{"Matn" if scores.get("fourth") == "passage" else "Gapirish"} '
            f'{h(scores.get("speaking","—"))}</p>'
        )

    return HTMLResponse(f"""<html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Arabiy — sertifikat tekshiruvi</title></head>
<body style="font-family:sans-serif;background:#FAF6EE;color:#26211A;text-align:center;padding:40px 16px">
<h1 style="color:#0E6B4E">✅ Haqiqiy sertifikat</h1>
<div style="max-width:420px;margin:0 auto;background:#FFFDF7;border:2px solid #C9A227;border-radius:16px;padding:24px">
<p style="font-size:22px;font-weight:bold;margin:4px">{h(cert.holder_name)}</p>
{body}
<p style="margin:4px">Sana: {cert.issued_at.strftime('%d.%m.%Y')}</p>
<p style="margin:4px;font-size:12px;color:#8A8071">ID: {h(cert.cert_id)}</p>
</div>
<p style="margin-top:24px"><a href="https://t.me/JamalArabiy_bot" style="color:#0E6B4E;font-weight:bold">🕌 Arabiy — arab tilini bepul o'rganing</a></p>
</body></html>""")
