"""Curriculum v2 API — yangi dars playeri endpointlari (K2).

/api/v2/* — v1 (jonli kurs) endpointlariga tegmaydi.
"""

import json
import random
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    DrillResult,
    LessonRating,
    MockResult,
    Plan,
    Progress,
    TutorMistake,
    TutorTurn,
    User,
    XpLog,
)
from db.session import get_session
from services.achievements import check_and_award
from services.curriculum import (
    load_curriculum,
    load_lesson_v2,
    written_lesson_ids,
)
from services.lesson_test import PASS_SCORE, build_test
from services.reading import passage_for
from services.srs import reset_words, seed_from_srs_cards
from services.stats import completed_lesson_ids, lesson_attempt_count, user_stats
from services.telegram_auth import get_current_user

router = APIRouter(prefix="/api/v2")

CHECKPOINT_EVERY = 5
CHECKPOINT_QUESTIONS = 15
CHECKPOINT_PASS = 70  # foiz
FAIL_XP = 5  # yiqilgan urinish uchun ham ozgina XP (streak uzilmasin)


@router.get("/lessons/{lesson_id}")
async def lesson_v2(
    lesson_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    meta = load_curriculum().get(lesson_id)
    data = load_lesson_v2(lesson_id)
    if not meta or not data:
        raise HTTPException(status_code=404, detail="Dars topilmadi")

    # Mikro-test urinishga qarab yig'iladi — qayta topshirganda boshqa savollar
    attempts = await lesson_attempt_count(session, user.id, lesson_id)
    test = build_test(lesson_id, attempts)

    return {
        **data,
        "micro_test": test["items"],
        "test_attempt": test["attempt"],
        "pass_score": PASS_SCORE,
        "attempts_made": attempts,
        # A2+ darslarda bosqichma-bosqich o'qish matni (services/reading.py)
        "passage": passage_for(lesson_id),
        "meta": {
            "title_uz": meta["title_uz"],
            "level": meta["level"],
            "order": meta["order"],
            "module": meta["module"],
        },
    }


class CompleteV2Body(BaseModel):
    correct: int = Field(ge=0)
    total: int = Field(ge=1)
    wrong_words: list[str] = Field(default_factory=list)


def _checkpoint_lessons(lesson_id: str) -> list[str]:
    """Nazorat testi qamrab oladigan 5 dars (agar bu dars 5-lik chegarasi bo'lsa)."""
    meta = load_curriculum().get(lesson_id)
    if not meta or meta["type"] != "lesson" or meta["order"] % CHECKPOINT_EVERY != 0:
        return []
    prefix = lesson_id.split("-")[0]
    ids = [
        f"{prefix}-{i:02d}"
        for i in range(meta["order"] - CHECKPOINT_EVERY + 1, meta["order"] + 1)
    ]
    written = written_lesson_ids()
    return [i for i in ids if i in written]


@router.post("/lessons/{lesson_id}/complete")
async def complete_v2(
    lesson_id: str,
    body: CompleteV2Body,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    data = load_lesson_v2(lesson_id)
    if not data:
        raise HTTPException(status_code=404, detail="Dars topilmadi")

    correct = min(body.correct, body.total)
    perfect = correct == body.total
    score = round(100 * correct / body.total)
    passed = score >= PASS_SCORE  # spec §11 — 60% dan past bo'lsa dars o'tilmaydi

    done_before = await completed_lesson_ids(session, user.id)
    first_time = lesson_id not in done_before
    if not passed:
        # Dars tugatilmadi: keyingi dars ochilmaydi, XP faqat urinish uchun
        xp = FAIL_XP
    else:
        xp = (10 + 2 * correct + (5 if perfect else 0)) if first_time else (5 + correct)

    session.add(
        Progress(
            user_id=user.id, lesson_id=lesson_id,
            correct=correct, total=body.total, xp_earned=xp,
            passed=1 if passed else 0,
        )
    )
    session.add(XpLog(user_id=user.id, amount=xp, source=f"lesson:{lesson_id}"))
    await session.commit()

    # SRS: yangi kartalar + xato so'zlar reset (spec §11)
    added = await seed_from_srs_cards(session, user.id, data.get("srs_cards", []))
    await reset_words(session, user.id, body.wrong_words)

    plan = (
        await session.execute(
            select(Plan).where(Plan.user_id == user.id).order_by(Plan.id.desc()).limit(1)
        )
    ).scalar_one_or_none()
    plan_order = json.loads(plan.module_order_json) if plan else None
    stats = await user_stats(session, user.id, plan_order)
    new_badges = await check_and_award(session, user.id, stats["streak"])

    cp = _checkpoint_lessons(lesson_id)
    return {
        "xp_earned": xp,
        "perfect": perfect,
        "score": score,
        "passed": passed,
        "pass_score": PASS_SCORE,
        "first_time": first_time,
        "srs_added": added,
        "srs_reset": len(body.wrong_words),
        "stats": stats,
        "new_badges": new_badges,
        # Yiqilgan darsdan keyin nazorat testi taklif qilinmaydi
        "checkpoint_available": passed and len(cp) >= 2,
    }


class RateBody(BaseModel):
    rating: int = Field(ge=-1, le=1)  # +1 (👍) yoki -1 (👎)


@router.post("/lessons/{lesson_id}/rate")
async def rate_lesson(
    lesson_id: str,
    body: RateBody,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Dars oxiridagi 1-bosishli baho (👍/👎). Takror bosilsa yangilanadi."""
    if body.rating == 0:
        return {"ok": False}
    existing = (
        await session.execute(
            select(LessonRating).where(
                LessonRating.user_id == user.id,
                LessonRating.lesson_id == lesson_id,
            )
        )
    ).scalar_one_or_none()
    if existing:
        existing.rating = body.rating
    else:
        session.add(
            LessonRating(user_id=user.id, lesson_id=lesson_id, rating=body.rating)
        )
    await session.commit()
    return {"ok": True}


@router.get("/checkpoint/{lesson_id}")
async def checkpoint_questions(
    lesson_id: str,
    user: User = Depends(get_current_user),
):
    ids = _checkpoint_lessons(lesson_id)
    if len(ids) < 2:
        raise HTTPException(status_code=404, detail="Nazorat testi mavjud emas")

    pool: list[dict] = []
    for lid in ids:
        data = load_lesson_v2(lid)
        if not data:
            continue
        for item in data.get("micro_test", []):
            pool.append(item)

    random.shuffle(pool)
    questions = pool[:CHECKPOINT_QUESTIONS]
    return {
        "lesson_ids": ids,
        "pass_percent": CHECKPOINT_PASS,
        "questions": questions,
    }


@router.post("/checkpoint/{lesson_id}/complete")
async def checkpoint_complete(
    lesson_id: str,
    body: CompleteV2Body,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if not _checkpoint_lessons(lesson_id):
        raise HTTPException(status_code=404, detail="Nazorat testi mavjud emas")

    correct = min(body.correct, body.total)
    score = round(100 * correct / body.total)
    passed = score >= CHECKPOINT_PASS

    xp = 15 + correct if passed else 5
    session.add(
        XpLog(user_id=user.id, amount=xp, source=f"checkpoint:{lesson_id}")
    )
    await session.commit()
    await reset_words(session, user.id, body.wrong_words)

    return {
        "score": score,
        "passed": passed,
        "xp_earned": xp,
        "srs_reset": len(body.wrong_words),
    }


# ─────────────────── AI rol o'yini (Saudiya vaziyatlari) ───────────────────


@router.get("/roleplay/scenarios")
async def roleplay_scenarios(user: User = Depends(get_current_user)):
    from services import roleplay

    return {"scenarios": roleplay.scenario_list()}


class RoleplayBody(BaseModel):
    scenario_id: str
    history: list[dict] = Field(default_factory=list)


@router.post("/roleplay/reply")
async def roleplay_reply(
    body: RoleplayBody,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    from services import ai_usage, roleplay

    if not body.history:
        op = roleplay.opening(body.scenario_id)
        if op is None:
            raise HTTPException(status_code=404, detail="Vaziyat topilmadi")
        return op
    # Faqat oxirgi 12 xabar (kontekstni cheklaymiz)
    out = await roleplay.reply(body.scenario_id, body.history[-12:])
    usage = out.pop("usage", None)
    if usage:
        ai_usage.record(session, "roleplay", usage, user.id)
        await session.commit()
    return out


# ─────────────────── AI yozish bahosi (zaxirali) ───────────────────


class WritingEvalBody(BaseModel):
    lesson_id: str
    text: str = Field(max_length=1000)


FALLBACK_FEEDBACK = (
    "AI baholash hozircha o'chiq. Yozganingiz saqlandi — asosiysi mashq "
    "qildingiz! Darsdagi namunalar bilan o'zingiz solishtirib ko'ring."
)


@router.post("/eval/writing")
async def eval_writing(
    body: WritingEvalBody,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    from config import settings
    from services import ai_usage

    lesson = load_lesson_v2(body.lesson_id) or {}
    task = (lesson.get("skills") or {}).get("writing", {}).get("task_uz", "")

    if not settings.anthropic_api_key or not body.text.strip():
        return {"ai": False, "feedback_uz": FALLBACK_FEEDBACK}

    try:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        resp = await client.messages.create(
            # Qisqa baho uchun Haiku yetarli — Opus'dan ~15x arzon
            model=settings.tutor_model,
            max_tokens=800,
            system=(
                "Sen arab tili o'qituvchisisan. O'zbek tilida so'zlashuvchi "
                "boshlang'ich o'quvchining yozma ishini bahola. Javobing qisqa "
                "(3-5 jumla), o'zbek tilida (lotin), samimiy va rag'batlantiruvchi. "
                "Xatolarni ko'rsat, to'g'ri variantini yoz. Baho qo'yma."
            ),
            messages=[
                {
                    "role": "user",
                    "content": f"Topshiriq: {task}\n\nO'quvchi yozgani:\n{body.text}",
                }
            ],
        )
        feedback = next(
            (b.text for b in resp.content if b.type == "text"), FALLBACK_FEEDBACK
        )
        ai_usage.record(session, "writing", ai_usage.usage_of(resp), user.id)
        await session.commit()
        return {"ai": True, "feedback_uz": feedback}
    except Exception:
        return {"ai": False, "feedback_uz": FALLBACK_FEEDBACK}


# ─────────────────── AI ustoz — jonli suhbat (K17) ───────────────────
# services/tutor.py (Haiku 4.5, structured output), services/stt.py (Groq
# Whisper), services/tts.py (edge-tts cache). Kunlik limit — token xarajati
# nazorati: har chaqiruv (ochilish ham) bitta "turn" sifatida sanaladi.

_SESSION_KEY_RE = r"^[A-Za-z0-9_-]{8,36}$"
_AUDIO_KEY_RE = re.compile(r"^[0-9a-f]{24}$")


async def _user_level(session: AsyncSession, user_id: int) -> str:
    plan = (
        await session.execute(
            select(Plan.level).where(Plan.user_id == user_id).order_by(Plan.id.desc()).limit(1)
        )
    ).scalar_one_or_none()
    return (plan or "A0").upper()


async def _tutor_turns_today(session: AsyncSession, user_id: int) -> int:
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start = start.replace(tzinfo=None)  # DB'da naive UTC (models.utcnow)
    n = (
        await session.execute(
            select(func.count(TutorTurn.id)).where(
                TutorTurn.user_id == user_id, TutorTurn.created_at >= start
            )
        )
    ).scalar_one()
    return int(n or 0)


async def _tutor_access(session: AsyncSession, user: User) -> dict:
    """VIP → to'liq limit; bepul → TUTOR_FREE_TURNS (tatib ko'rish)."""
    from config import settings
    from services import billing

    vip = billing.is_vip(user)
    limit = settings.tutor_daily_turns if vip else settings.tutor_free_turns
    used = await _tutor_turns_today(session, user.id)
    return {
        "vip": vip,
        "vip_days_left": billing.vip_days_left(user),
        "daily_limit": limit,
        "turns_left": max(limit - used, 0),
        "used": used,
    }


@router.get("/tutor/topics")
async def tutor_topics(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    from config import settings
    from services import billing, stt, tutor

    level = await _user_level(session, user.id)
    access = await _tutor_access(session, user)
    # So'nggi mock natijalari — o'quvchi o'sishini ko'rsin
    recent = (
        await session.execute(
            select(MockResult.mock_id, MockResult.score, MockResult.created_at)
            .where(MockResult.user_id == user.id)
            .order_by(MockResult.id.desc())
            .limit(10)
        )
    ).all()
    return {
        "level": level,
        "topics": tutor.topic_list(level),
        "mocks": tutor.mock_list(level),
        "mock_results": [
            {"mock_id": r[0], "score": r[1], "date": r[2].strftime("%d.%m")} for r in recent
        ],
        **{k: v for k, v in access.items() if k != "used"},
        "free_turns": settings.tutor_free_turns,
        "vip_turns": settings.tutor_daily_turns,
        "price": billing.price_summary(),
        "ai": bool(settings.anthropic_api_key),
        "voice": stt.available(),
    }


class TutorTurnBody(BaseModel):
    session_key: str = Field(pattern=_SESSION_KEY_RE)
    topic_id: str = Field(default="erkin", max_length=24)
    # [{role:'user'|'assistant', content}] — assistant = faqat `ar` matni
    history: list[dict] = Field(default_factory=list, max_length=60)
    voice: bool = False  # oxirgi javob mikrofondan keldi
    mode: str = Field(default="chat", pattern=r"^(chat|mock)$")
    mock_id: str = Field(default="", max_length=24)


@router.post("/tutor/turn")
async def tutor_turn(
    body: TutorTurnBody,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    from config import settings
    from services import ai_usage, alerts, tts, tutor

    if not settings.anthropic_api_key:
        raise HTTPException(status_code=503, detail="AI ustoz hozircha o'chiq")

    access = await _tutor_access(session, user)
    if access["turns_left"] <= 0:
        if not access["vip"]:
            # 402 — klient paywall'ni ochadi
            raise HTTPException(
                status_code=402, detail="Bepul javoblar tugadi — VIP bilan davom eting"
            )
        raise HTTPException(
            status_code=429, detail="Bugungi suhbat limiti tugadi — ertaga davom eting"
        )

    level = await _user_level(session, user.id)
    known = await tutor.known_words(session, user.id)
    for m in body.history:
        if len(str(m.get("content", ""))) > 600:
            raise HTTPException(status_code=422, detail="Xabar juda uzun")

    learner_answered = bool(body.history) and body.history[-1].get("role") == "user"
    try:
        if body.mode == "mock":
            reply, usage = await tutor.reply_mock(
                name=user.name,
                level=level,
                mock_id=body.mock_id,
                history=body.history,
                known=known,
            )
            ok = reply.score >= 50 if learner_answered else True
            score = reply.score if learner_answered else -1
        else:
            reply, usage = await tutor.reply(
                name=user.name,
                level=level,
                topic_id=body.topic_id,
                history=body.history,
                known=known,
            )
            ok = reply.correction_ok if learner_answered else True
            score = -1
    except tutor.TutorUnavailable as e:
        # Turn hisobga olinmaydi — o'quvchi limiti kuymaydi. Kredit/kalit
        # muammosi — admin Telegram'da darhol biladi (kuniga bir marta)
        if e.kind in ("credit", "auth"):
            alerts.fire(getattr(request.app.state, "bot", None), e.kind)
        raise HTTPException(status_code=503, detail=e.message_uz)

    ai_usage.record(session, "mock" if body.mode == "mock" else "tutor", usage, user.id)
    if learner_answered:
        await _note_mistake(session, user.id, body, reply, score)
    # O'quvchi javob bergan turn (ochilish emas) — limit va statistika uchun
    session.add(
        TutorTurn(
            user_id=user.id,
            session_key=body.session_key,
            topic=(body.mock_id if body.mode == "mock" else body.topic_id)[:24],
            level=level,
            ok=1 if ok else 0,
            voice=1 if (learner_answered and body.voice) else 0,
            mode=body.mode,
            score=score,
        )
    )
    await session.commit()

    # Matn darhol ketadi, mp3 fonda tayyorlanadi (edge-tts 1-3 s) — klient
    # audio'ni kechroq, tayyor bo'lganda yuklaydi (audio.ts: playUrl retry)
    audio_key = tts.schedule(reply.ar, level)
    return {
        "reply": reply.model_dump(),
        "audio_url": f"/api/v2/tutor/audio/{audio_key}.mp3" if audio_key else "",
        "turns_left": max(access["turns_left"] - 1, 0),
        "vip": access["vip"],
        "usage": usage,
    }


MISTAKE_KEEP = 300  # har o'quvchi uchun daftarda saqlanadigan eng ko'p yozuv
MOCK_MISTAKE_BELOW = 70  # mock javobi shundan past bo'lsa daftarga tushadi


async def _note_mistake(session: AsyncSession, user_id: int, body, reply, score: int) -> None:
    """Xatolar daftari: ustoz tuzatgan jumla (chat) yoki past mock javobi.
    O'quvchi keyin ko'rib, eshitib, qayta aytib mashq qiladi (/tutor/log)."""
    said = str(body.history[-1].get("content", "")).removeprefix("🎤").strip()[:400]
    if not said:
        return
    if body.mode == "mock":
        if not (0 <= score < MOCK_MISTAKE_BELOW) or not getattr(reply, "ideal_ar", ""):
            return
        row = TutorMistake(
            user_id=user_id, kind="mock", topic=body.mock_id[:24], said_ar=said,
            fixed_ar=reply.ideal_ar[:400], note_uz=(reply.feedback_uz or "")[:400],
        )
    else:
        if reply.correction_ok or not reply.fixed_ar:
            return
        row = TutorMistake(
            user_id=user_id, kind="chat", topic=body.topic_id[:24], said_ar=said,
            fixed_ar=reply.fixed_ar[:400], note_uz=(reply.note_uz or "")[:400],
        )
    session.add(row)
    # Daftar cheksiz o'smasin — eng eskilari o'chadi
    ids = (
        await session.execute(
            select(TutorMistake.id)
            .where(TutorMistake.user_id == user_id)
            .order_by(TutorMistake.id.desc())
            .offset(MISTAKE_KEEP)  # yangi qator autoflush bilan hisobda
        )
    ).scalars().all()
    for mid in ids:
        old = await session.get(TutorMistake, mid)
        if old is not None:
            await session.delete(old)


@router.get("/tutor/audio/{key}.mp3")
async def tutor_audio(key: str):
    """Ustoz javobining mp3'si. Kalit — matn xeshi, sirli ma'lumot yo'q,
    shuning uchun <audio src> to'g'ridan-to'g'ri (initData'siz) yuklay oladi."""
    from services import tts

    if not _AUDIO_KEY_RE.match(key):
        raise HTTPException(status_code=404)
    path = tts.path_for(key)
    if not path.exists():
        # Fonda hali tayyorlanayotgan bo'lsa — biroz kutamiz (klient retry ham qiladi)
        await tts.wait_for(key, timeout=6)
    if not path.exists():
        raise HTTPException(status_code=404)
    return FileResponse(
        path, media_type="audio/mpeg", headers={"Cache-Control": "public, max-age=604800"}
    )


async def _read_audio(file: UploadFile) -> bytes:
    from services.stt import MAX_AUDIO_BYTES

    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="Audio bo'sh")
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio juda uzun (maks. 20 soniya)")
    return data


STT_DAILY_CAP = 200  # har o'quvchi kuniga shuncha ovoz yozuvi — Groq bepul limiti himoyasi
_stt_used: dict[int, tuple[str, int]] = {}


def _stt_quota(user_id: int) -> None:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    d, n = _stt_used.get(user_id, (day, 0))
    if d != day:
        n = 0
    if n >= STT_DAILY_CAP:
        raise HTTPException(status_code=429, detail="Bugungi ovoz limiti tugadi — ertaga davom eting")
    _stt_used[user_id] = (day, n + 1)


def _stt_failed(request: Request) -> None:
    """STT xizmat xatosi (kalit/tarmoq) — o'quvchiga 503, adminga ogohlantirish.
    Oddiy «tushunilmadi» (bo'sh matn, 200) va yaroqsiz audio (400) bu yerga kirmaydi."""
    from services import alerts, stt

    err = stt.last_error
    if not err or err == "http:400":
        return
    bot = getattr(request.app.state, "bot", None)
    if err == "auth":
        alerts.fire(bot, "stt_auth")
    else:
        alerts.fire(bot, "stt_down", err)
    raise HTTPException(
        status_code=503, detail="Ovoz xizmati vaqtincha ishlamayapti — admin xabardor."
    )


@router.post("/tutor/transcribe")
async def tutor_transcribe(
    request: Request,
    file: UploadFile = File(...),
    prompt: str = Form(""),
    user: User = Depends(get_current_user),
):
    """Mikrofon yozuvi → arabcha matn. `prompt` — oxirgi ustoz savoli (kontekst)."""
    from services import stt

    if not stt.available():
        raise HTTPException(status_code=503, detail="Ovoz xizmati sozlanmagan")
    data = await _read_audio(file)
    _stt_quota(user.id)
    text = await stt.transcribe(
        data, file.filename or "speech.webm", file.content_type or "audio/webm", prompt[:300]
    )
    if not text:
        _stt_failed(request)
    return {"text": text}


@router.post("/tutor/pronounce")
async def tutor_pronounce(
    request: Request,
    file: UploadFile = File(...),
    target: str = Form("", max_length=400),
    drill_key: str = Form("", max_length=32),
    idx: int = Form(-1),
    user: User = Depends(get_current_user),
):
    """Takrorlash mashqi: o'quvchi jumlani aytadi → o'xshashlik bali.
    Whisper'ga maqsad matn BERILMAYDI — aks holda «eshitgandek» yozib qo'yadi.
    Talaffuz mashqida (drill_key+idx) maqsadni server o'zi biladi."""
    from services import drill, stt, tutor

    if not stt.available():
        raise HTTPException(status_code=503, detail="Ovoz xizmati sozlanmagan")
    if drill_key:
        target = drill.target(drill_key, user.id, idx)
        if not target:
            raise HTTPException(status_code=404, detail="Mashq topilmadi — qaytadan boshlang")
    if not target.strip():
        raise HTTPException(status_code=422, detail="Maqsad jumla yo'q")
    data = await _read_audio(file)
    _stt_quota(user.id)
    heard = await stt.transcribe(
        data, file.filename or "speech.webm", file.content_type or "audio/webm"
    )
    if not heard:
        _stt_failed(request)
    result = tutor.pronunciation_score(target, heard)
    if drill_key:
        drill.record(drill_key, user.id, idx, result["score"])
    return {"transcript": heard, **result}


# ─────────── Talaffuz mashqi (K17.5) — LLM'siz, bepul ───────────


@router.get("/tutor/drill")
async def tutor_drill(
    topic_id: str = "erkin",
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Mavzu bo'yicha 10 ta jumla (audio fonda tayyorlanadi). VIP shart emas."""
    from services import drill, stt, tts

    level = await _user_level(session, user.id)
    key, items = drill.create(user.id, level, topic_id[:24])
    out = []
    for i, it in enumerate(items):
        audio_key = tts.schedule(it["ar"], level)
        out.append(
            {
                "idx": i,
                **it,
                "audio_url": f"/api/v2/tutor/audio/{audio_key}.mp3" if audio_key else "",
            }
        )
    return {
        "key": key,
        "level": level,
        "topic_id": topic_id if topic_id in drill.TOPIC_BY_ID else "erkin",
        "items": out,
        "voice": stt.available(),
    }


class DrillFinishBody(BaseModel):
    key: str = Field(min_length=8, max_length=32)


@router.post("/tutor/drill/finish")
async def tutor_drill_finish(
    body: DrillFinishBody,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Mashq yakuni: o'rtacha ball, XP (kamida 5 jumla; bir mavzu kuniga bir marta)."""
    from services import drill

    s = drill.summary(body.key, user.id)
    if s is None:
        raise HTTPException(status_code=404, detail="Mashq topilmadi")
    xp = drill.xp_for(s["score"], s["count"])
    if xp > 0:
        today = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0, tzinfo=None
        )
        earned = (
            await session.execute(
                select(DrillResult.id)
                .where(
                    DrillResult.user_id == user.id,
                    DrillResult.topic == s["topic"],
                    DrillResult.xp > 0,
                    DrillResult.created_at >= today,
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if earned is not None:
            xp = 0
    if s["count"] > 0:
        session.add(
            DrillResult(
                user_id=user.id, topic=s["topic"], level=s["level"],
                score=s["score"], count=s["count"], xp=xp,
            )
        )
        if xp > 0:
            session.add(XpLog(user_id=user.id, amount=xp, source=f"drill:{body.key}"))
        await session.commit()
    drill.finish(body.key, user.id)
    return {
        "topic_id": s["topic"],
        "score": s["score"],
        "count": s["count"],
        "total": len(s["items"]),
        "xp": xp,
        "scores": s["scores"],
        "items": [{"ar": it["ar"], "uz": it["uz"]} for it in s["items"]],
    }


@router.get("/tutor/log")
async def tutor_log(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Speaking daftari: xatolar (tuzatishlar), mock va talaffuz natijalari tarixi."""
    from services import tutor

    rows = (
        await session.execute(
            select(TutorMistake)
            .where(TutorMistake.user_id == user.id)
            .order_by(TutorMistake.id.desc())
            .limit(100)
        )
    ).scalars().all()
    mistakes = [
        {
            "id": m.id,
            "kind": m.kind,
            "topic": m.topic,
            "title": (
                (tutor.MOCK_BY_ID.get(m.topic) or tutor.TOPIC_BY_ID.get(m.topic) or {}).get("title_uz", "")
            ),
            "said_ar": m.said_ar,
            "fixed_ar": m.fixed_ar,
            "note_uz": m.note_uz,
            "date": m.created_at.strftime("%d.%m"),
        }
        for m in rows
    ]

    mock_rows = (
        await session.execute(
            select(MockResult.mock_id, MockResult.score, MockResult.created_at)
            .where(MockResult.user_id == user.id)
            .order_by(MockResult.id.asc())
        )
    ).all()
    mocks: dict[str, dict] = {}
    for mock_id, score, created in mock_rows:
        m = tutor.MOCK_BY_ID.get(mock_id) or {}
        d = mocks.setdefault(
            mock_id,
            {
                "mock_id": mock_id, "title": m.get("title_uz", mock_id), "emoji": m.get("emoji", "🎯"),
                "best": 0, "last": 0, "attempts": 0, "history": [], "date": "",
            },
        )
        d["attempts"] += 1
        d["best"] = max(d["best"], score)
        d["last"] = score
        d["date"] = created.strftime("%d.%m")
        d["history"] = (d["history"] + [score])[-6:]

    drill_rows = (
        await session.execute(
            select(DrillResult.topic, DrillResult.score, DrillResult.created_at)
            .where(DrillResult.user_id == user.id)
            .order_by(DrillResult.id.asc())
        )
    ).all()
    drills: dict[str, dict] = {}
    for topic_id, score, created in drill_rows:
        t = tutor.TOPIC_BY_ID.get(topic_id) or {}
        d = drills.setdefault(
            topic_id,
            {
                "topic_id": topic_id, "title": t.get("title_uz", topic_id), "emoji": t.get("emoji", "🎤"),
                "best": 0, "last": 0, "attempts": 0, "history": [], "date": "",
            },
        )
        d["attempts"] += 1
        d["best"] = max(d["best"], score)
        d["last"] = score
        d["date"] = created.strftime("%d.%m")
        d["history"] = (d["history"] + [score])[-6:]

    return {
        "mistakes": mistakes,
        "mocks": sorted(mocks.values(), key=lambda d: -d["best"]),
        "drills": sorted(drills.values(), key=lambda d: -d["best"]),
    }


class SayBody(BaseModel):
    text: str = Field(min_length=1, max_length=400)


@router.post("/tutor/say")
async def tutor_say(
    body: SayBody,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Ixtiyoriy arabcha matn uchun mp3 (xatolar daftari: to'g'ri jumlani eshitish).
    Matn xeshi bilan keshlanadi — bir xil jumla bir marta sintez qilinadi."""
    from services import tts

    level = await _user_level(session, user.id)
    key = tts.schedule(body.text.strip(), level)
    return {"audio_url": f"/api/v2/tutor/audio/{key}.mp3" if key else ""}


@router.delete("/tutor/mistakes/{mistake_id}")
async def tutor_mistake_delete(
    mistake_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """«O'rgandim» — daftardan o'chirish."""
    row = await session.get(TutorMistake, mistake_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Topilmadi")
    await session.delete(row)
    await session.commit()
    return {"ok": True}


class TutorFinishBody(BaseModel):
    session_key: str = Field(pattern=_SESSION_KEY_RE)


MOCK_XP_FACTOR = 0.5  # 100 ball = 50 XP; bir mock uchun kuniga bir marta


@router.post("/tutor/finish")
async def tutor_finish(
    body: TutorFinishBody,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Suhbat/mock yakuni: XP (bir marta) va qisqa hisobot.

    Mock: o'rtacha ball → MockResult, XP = ball × MOCK_XP_FACTOR (bir mock
    uchun kuniga bir marta — farmga yo'l qo'ymaslik uchun)."""
    from services import tutor

    rows = (
        await session.execute(
            select(TutorTurn.ok, TutorTurn.voice, TutorTurn.mode, TutorTurn.score, TutorTurn.topic)
            .where(TutorTurn.user_id == user.id, TutorTurn.session_key == body.session_key)
            .order_by(TutorTurn.id.asc())
        )
    ).all()
    # Ochilish turn'i (o'quvchi javobsiz) ham qatorga yoziladi — uni hisobdan
    # chiqarish uchun: javoblar = qatorlar - 1
    turns = max(len(rows) - 1, 0)
    ok = sum(1 for r in rows if r[0]) - (1 if rows else 0)
    ok = max(min(ok, turns), 0)
    voice = sum(1 for r in rows if r[1])
    is_mock = bool(rows) and rows[0][2] == "mock"

    source = f"tutor:{body.session_key}"
    already = (
        await session.execute(
            select(XpLog.id).where(XpLog.user_id == user.id, XpLog.source == source).limit(1)
        )
    ).scalar_one_or_none()
    xp = 0
    result: dict = {"turns": turns, "ok_turns": ok, "voice_turns": voice}

    if is_mock:
        scores = [r[3] for r in rows if r[3] >= 0]
        avg = round(sum(scores) / len(scores)) if scores else 0
        mock_id = rows[0][4]
        level = await _user_level(session, user.id)
        result.update({"mock": True, "score": avg, "scores": scores, "mock_id": mock_id})
        if scores and already is None:
            today = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0, tzinfo=None
            )
            earned_today = (
                await session.execute(
                    select(MockResult.id)
                    .where(
                        MockResult.user_id == user.id,
                        MockResult.mock_id == mock_id,
                        MockResult.xp > 0,
                        MockResult.created_at >= today,
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            # Faqat to'liq (barcha savollar) mock XP beradi
            if earned_today is None and len(scores) >= tutor.MOCK_QUESTIONS:
                xp = round(avg * MOCK_XP_FACTOR)
            session.add(
                MockResult(
                    user_id=user.id,
                    mock_id=mock_id,
                    level=level,
                    score=avg,
                    xp=xp,
                    session_key=body.session_key,
                )
            )
            if xp > 0:
                session.add(XpLog(user_id=user.id, amount=xp, source=source))
            await session.commit()
    elif turns >= 3 and already is None:
        xp = min(30, 2 * turns + ok + 2 * voice)
        session.add(XpLog(user_id=user.id, amount=xp, source=source))
        await session.commit()

    result["xp"] = xp
    return result


class TutorSaveWordBody(BaseModel):
    ar: str = Field(min_length=1, max_length=128)
    uz: str = Field(default="", max_length=256)


@router.post("/tutor/save_word")
async def tutor_save_word(
    body: TutorSaveWordBody,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Suhbatda chiqqan yangi so'zni SRS kartotekasiga qo'shish."""
    added = await seed_from_srs_cards(
        session, user.id, [{"front": body.ar.strip(), "back": body.uz.strip(), "type": "word"}]
    )
    await session.commit()
    return {"added": added}
