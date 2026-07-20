"""Imtihon + sertifikat API (K3)."""

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Certificate, ExamAttempt, Plan, User, XpLog
from db.session import get_session
from services import exam as exam_svc
from services.certificate import issue_certificate
from services.telegram_auth import get_current_user

router = APIRouter()

PASS_XP = 50


async def _user_level(session: AsyncSession, user_id: int) -> str:
    plan = (
        await session.execute(
            select(Plan).where(Plan.user_id == user_id).order_by(Plan.id.desc()).limit(1)
        )
    ).scalar_one_or_none()
    return plan.level if plan else "A0"


@router.get("/api/exam/info")
async def exam_info(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    level = await _user_level(session, user.id)
    available = exam_svc.exam_available(level)
    cooldown = await exam_svc.cooldown_until(session, user.id, level)
    passed = await exam_svc.already_passed(session, user.id, level)
    pool = exam_svc.load_pool(level) if available else None

    done, total = await exam_svc.level_progress(session, user.id, level)
    needed = exam_svc.unlock_threshold(total)
    # Bir marta o'tgan bo'lsa — qayta topshirish har doim ochiq
    unlocked = done >= needed or passed

    return {
        "level": level,
        "available": available,
        "already_passed": passed,
        "cooldown_until": cooldown.isoformat() if cooldown else None,
        "minutes": pool["config"]["minutes"] if pool else 0,
        "counts": pool["config"] if pool else {},
        # Darslar qulfi (80%)
        "unlocked": unlocked,
        "lessons_done": done,
        "lessons_total": total,
        "lessons_needed": needed,
        "next_level": exam_svc.next_level(level),
    }


@router.post("/api/exam/start")
async def exam_start(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    level = await _user_level(session, user.id)
    if not exam_svc.exam_available(level):
        raise HTTPException(status_code=404, detail="Bu daraja uchun imtihon hali yo'q")

    done, total = await exam_svc.level_progress(session, user.id, level)
    needed = exam_svc.unlock_threshold(total)
    already = await exam_svc.already_passed(session, user.id, level)
    if done < needed and not already:
        raise HTTPException(
            status_code=403,
            detail=f"Imtihon uchun {needed} ta dars kerak — hozir {done} ta tugatilgan",
        )

    cooldown = await exam_svc.cooldown_until(session, user.id, level)
    if cooldown:
        raise HTTPException(
            status_code=429,
            detail=f"Qayta topshirish: {cooldown.isoformat()} dan keyin",
        )
    exam = exam_svc.build_exam(level)
    attempt = await exam_svc.start_attempt(session, user.id, level, exam)
    return {"attempt_id": attempt.id, **exam}


class SubmitBody(BaseModel):
    attempt_id: int
    reading_correct: int = Field(ge=0)
    listening_correct: int = Field(ge=0)
    writing_score: int = Field(ge=0, le=100)
    speaking_score: int = Field(ge=0, le=100)
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

    result = exam_svc.grade(
        attempt,
        body.reading_correct,
        body.listening_correct,
        body.writing_score,
        body.speaking_score,
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
        if plan and nxt and plan.level == attempt.level:
            plan.level = nxt
            session.add(plan)
            promoted_to = nxt

        await session.commit()

        holder = body.holder_name.strip() or user.name
        cert = await issue_certificate(
            session, user.id, holder, attempt.level, result["total"],
            {k: result[k] for k in ("reading", "listening", "writing", "speaking")},
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
                    f"Men Arabiy'da {attempt.level} darajasini tugatdim! 🎓"
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
                        f"🏅 Tabriklaymiz! {attempt.level} darajasi "
                        f"sertifikati — {result['total']}/100"
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


@router.get("/api/verify/{code}")
async def verify(code: str, session: AsyncSession = Depends(get_session)):
    """Ochiq tekshirish sahifasi (authsiz) — QR shu yerga olib keladi."""
    cert = (
        await session.execute(
            select(Certificate).where(
                Certificate.cert_id.like(f"%-{code}"),
                Certificate.revoked == 0,
            )
        )
    ).scalar_one_or_none()

    if cert is None:
        return HTMLResponse(
            "<html><body style='font-family:sans-serif;text-align:center;padding:60px'>"
            "<h2>❌ Sertifikat topilmadi</h2></body></html>",
            status_code=404,
        )

    scores = json.loads(cert.scores_json or "{}")
    if (cert.kind or "level") == "weekly":
        rank = scores.get("rank", cert.level.lstrip("W") or "—")
        body = (
            f'<p style="margin:4px">Haftalik reyting: <b>{rank}-o\'rin</b></p>'
            f'<p style="margin:4px">Haftalik XP: <b>{cert.score}</b></p>'
            f'<p style="margin:4px;font-size:13px;color:#8A8071">Hafta: {scores.get("week","—")}</p>'
        )
    else:
        body = (
            f'<p style="margin:4px">Daraja: <b>{cert.level}</b></p>'
            f'<p style="margin:4px">Ball: <b>{cert.score}/100</b></p>'
            f'<p style="margin:4px;font-size:13px;color:#8A8071">'
            f'O\'qish {scores.get("reading","—")} · Tinglash {scores.get("listening","—")} · '
            f'Yozish {scores.get("writing","—")} · Gapirish {scores.get("speaking","—")}</p>'
        )

    return HTMLResponse(f"""<html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Arabiy — sertifikat tekshiruvi</title></head>
<body style="font-family:sans-serif;background:#FAF6EE;color:#26211A;text-align:center;padding:40px 16px">
<h1 style="color:#0E6B4E">✅ Haqiqiy sertifikat</h1>
<div style="max-width:420px;margin:0 auto;background:#FFFDF7;border:2px solid #C9A227;border-radius:16px;padding:24px">
<p style="font-size:22px;font-weight:bold;margin:4px">{cert.holder_name}</p>
{body}
<p style="margin:4px">Sana: {cert.issued_at.strftime('%d.%m.%Y')}</p>
<p style="margin:4px;font-size:12px;color:#8A8071">ID: {cert.cert_id}</p>
</div>
<p style="margin-top:24px"><a href="https://t.me/JamalArabiy_bot" style="color:#0E6B4E;font-weight:bold">🕌 Arabiy — arab tilini bepul o'rganing</a></p>
</body></html>""")
