"""Admin statistikasi — bot foydalanuvchilari va faollik haqida ma'lumot."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    Achievement,
    ExamAttempt,
    Feedback,
    LessonRating,
    MockResult,
    PaymentRequest,
    Plan,
    Progress,
    TutorRating,
    TutorTurn,
    User,
    UserWord,
    XpLog,
    utcnow,
)
from services.stats import TASHKENT_OFFSET, _local_date, _today


def _day_start_utc(d) -> datetime:
    """Toshkent sanasi 00:00 → naive UTC datetime.

    DIQQAT: isoformat() MATNI qaytarilmaydi — SQLite datetime'ni
    "2026-07-19 21:00:00" ko'rinishida saqlaydi va u "2026-07-19T19:00:00"
    matnidan KICHIK sanaladi (probel < "T"). Natijada kunning dastlabki
    5 soatidagi XP hisobga olinmay qolardi.
    """
    local_midnight = datetime(d.year, d.month, d.day)
    return local_midnight - TASHKENT_OFFSET


async def overview(session: AsyncSession) -> str:
    today = _today()
    today_start = _day_start_utc(today)
    week_start = _day_start_utc(today - timedelta(days=6))

    async def scalar(q):
        return (await session.execute(q)).scalar_one()

    real = User.is_demo == 0

    total_users = await scalar(
        select(func.count()).select_from(User).where(real)
    )
    onboarded = await scalar(
        select(func.count(func.distinct(Plan.user_id)))
    )
    new_today = await scalar(
        select(func.count()).select_from(User).where(
            real, User.created_at >= today_start
        )
    )
    new_week = await scalar(
        select(func.count()).select_from(User).where(
            real, User.created_at >= week_start
        )
    )

    active_today = await scalar(
        select(func.count(func.distinct(XpLog.user_id)))
        .select_from(XpLog)
        .join(User, User.id == XpLog.user_id)
        .where(real, XpLog.created_at >= today_start)
    )
    active_week = await scalar(
        select(func.count(func.distinct(XpLog.user_id)))
        .select_from(XpLog)
        .join(User, User.id == XpLog.user_id)
        .where(real, XpLog.created_at >= week_start)
    )

    lessons_done = await scalar(
        select(func.count())
        .select_from(Progress)
        .join(User, User.id == Progress.user_id)
        .where(real)
    )
    total_xp = await scalar(
        select(func.coalesce(func.sum(XpLog.amount), 0))
        .select_from(XpLog)
        .join(User, User.id == XpLog.user_id)
        .where(real)
    )
    reviews = await scalar(
        select(func.count())
        .select_from(XpLog)
        .join(User, User.id == XpLog.user_id)
        .where(real, XpLog.source == "review")
    )
    badges = await scalar(
        select(func.count())
        .select_from(Achievement)
        .join(User, User.id == Achievement.user_id)
        .where(real)
    )
    words = await scalar(
        select(func.count())
        .select_from(UserWord)
        .join(User, User.id == UserWord.user_id)
        .where(real)
    )

    # Daraja taqsimoti (har foydalanuvchining oxirgi rejasi)
    latest_plan = (
        select(Plan.user_id, func.max(Plan.id).label("mid"))
        .group_by(Plan.user_id)
        .subquery()
    )
    level_rows = (
        await session.execute(
            select(Plan.level, func.count())
            .join(latest_plan, latest_plan.c.mid == Plan.id)
            .group_by(Plan.level)
        )
    ).all()
    level_dist = " · ".join(f"{lvl}: {cnt}" for lvl, cnt in sorted(level_rows)) or "—"

    return (
        "📊 <b>Arabiy — Admin panel</b>\n\n"
        "👥 <b>Foydalanuvchilar</b>\n"
        f"• Jami: <b>{total_users}</b>\n"
        f"• Ro'yxatdan o'tgan (reja tuzgan): <b>{onboarded}</b>\n"
        f"• Bugun yangi: <b>{new_today}</b> · 7 kunda: <b>{new_week}</b>\n\n"
        "🔥 <b>Faollik</b>\n"
        f"• Bugun faol: <b>{active_today}</b>\n"
        f"• 7 kunda faol: <b>{active_week}</b>\n\n"
        "📚 <b>O'quv</b>\n"
        f"• Tugatilgan darslar: <b>{lessons_done}</b>\n"
        f"• Takror kartalari: <b>{words}</b>\n"
        f"• Takror mashqlari: <b>{reviews}</b>\n"
        f"• Jami XP: <b>{total_xp}</b>\n"
        f"• Berilgan yutuqlar: <b>{badges}</b>\n\n"
        "🎯 <b>Darajalar</b>\n"
        f"• {level_dist}\n\n"
        "ℹ️ Buyruqlar: /stats /users /user /broadcast /oktagon"
    )


async def recent_users(session: AsyncSession, limit: int = 15) -> str:
    rows = (
        await session.execute(
            select(User)
            .where(User.is_demo == 0)
            .order_by(User.id.desc())
            .limit(limit)
        )
    ).scalars().all()

    if not rows:
        return "Hozircha foydalanuvchilar yo'q."

    lines = [f"👥 <b>Oxirgi {len(rows)} foydalanuvchi</b>\n"]
    for u in rows:
        # Har biriga qisqa: daraja, darslar, XP
        plan = (
            await session.execute(
                select(Plan.level)
                .where(Plan.user_id == u.id)
                .order_by(Plan.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        lessons = (
            await session.execute(
                select(func.count()).select_from(Progress).where(
                    Progress.user_id == u.id
                )
            )
        ).scalar_one()
        joined = _local_date(u.created_at).isoformat()
        uname = f"@{u.username}" if u.username else "—"
        name = u.name or "Ismsiz"
        level = plan or "reja yo‘q"
        lines.append(
            f"• <b>{name}</b> ({uname}) · ID <code>{u.tg_id}</code>\n"
            f"  {level} · {lessons} dars · {joined}"
        )
    return "\n".join(lines)


async def user_detail(session: AsyncSession, tg_id: int) -> str:
    user = (
        await session.execute(select(User).where(User.tg_id == tg_id))
    ).scalar_one_or_none()
    if user is None:
        return f"❌ <code>{tg_id}</code> ID'li foydalanuvchi topilmadi."

    plan = (
        await session.execute(
            select(Plan)
            .where(Plan.user_id == user.id)
            .order_by(Plan.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    lessons = (
        await session.execute(
            select(func.count()).select_from(Progress).where(
                Progress.user_id == user.id
            )
        )
    ).scalar_one()
    total_xp = (
        await session.execute(
            select(func.coalesce(func.sum(XpLog.amount), 0)).where(
                XpLog.user_id == user.id
            )
        )
    ).scalar_one()
    words = (
        await session.execute(
            select(func.count()).select_from(UserWord).where(
                UserWord.user_id == user.id
            )
        )
    ).scalar_one()
    badges = (
        await session.execute(
            select(func.count()).select_from(Achievement).where(
                Achievement.user_id == user.id
            )
        )
    ).scalar_one()
    last_xp = (
        await session.execute(
            select(func.max(XpLog.created_at)).where(XpLog.user_id == user.id)
        )
    ).scalar_one()

    uname = f"@{user.username}" if user.username else "—"
    plan_line = (
        f"{plan.level} → {plan.target_level} ({plan.target_date}), "
        f"kunlik {plan.daily_xp_goal} XP"
        if plan
        else "reja tuzmagan"
    )
    last = _local_date(last_xp).isoformat() if last_xp else "—"

    return (
        f"👤 <b>{user.name or 'Ismsiz'}</b> ({uname})\n"
        f"ID: <code>{user.tg_id}</code>\n"
        f"Ro'yxatdan o'tgan: {_local_date(user.created_at).isoformat()}\n"
        f"Oxirgi faollik: {last}\n\n"
        f"📋 Reja: {plan_line}\n"
        f"📚 Darslar: {lessons}\n"
        f"🔁 Takror kartalari: {words}\n"
        f"💎 Jami XP: {total_xp}\n"
        f"🏆 Yutuqlar: {badges}"
    )


def _bar(frac: float, width: int = 10) -> str:
    filled = round(frac * width)
    return "█" * filled + "░" * (width - filled)


async def funnel(session: AsyncSession, level: str = "A0") -> str:
    """Voronka: onboarding→1-dars→daraja yakuni→imtihon + dars drop-off."""
    from services.curriculum import load_curriculum

    cur = load_curriculum()
    lvl_ids = [
        lid for lid, m in cur.items()
        if m["level"] == level and m["type"] == "lesson"
    ]
    lvl_ids.sort(key=lambda x: cur[x]["order"])
    lvl_set = set(lvl_ids)

    async def scalar(q):
        return (await session.execute(q)).scalar_one()

    real = User.is_demo == 0

    total = await scalar(select(func.count()).select_from(User).where(real))
    onboarded = await scalar(
        select(func.count(func.distinct(Plan.user_id)))
        .select_from(Plan).join(User, User.id == Plan.user_id).where(real)
    )

    # Har foydalanuvchi tugatgan (level) darslari
    rows = (
        await session.execute(
            select(Progress.user_id, Progress.lesson_id)
            .join(User, User.id == Progress.user_id)
            .where(real, Progress.lesson_id.in_(lvl_set))
            .distinct()
        )
    ).all()
    done_by_user: dict[int, set[str]] = {}
    per_lesson: dict[str, int] = {lid: 0 for lid in lvl_ids}
    for uid, lid in rows:
        done_by_user.setdefault(uid, set()).add(lid)
        per_lesson[lid] += 1

    started = len(done_by_user)
    completed_all = sum(1 for s in done_by_user.values() if lvl_set <= s)

    # Imtihon
    exam_finished = await scalar(
        select(func.count(func.distinct(ExamAttempt.user_id)))
        .select_from(ExamAttempt).join(User, User.id == ExamAttempt.user_id)
        .where(real, ExamAttempt.level == level, ExamAttempt.finished_at.isnot(None))
    )
    exam_passed = await scalar(
        select(func.count(func.distinct(ExamAttempt.user_id)))
        .select_from(ExamAttempt).join(User, User.id == ExamAttempt.user_id)
        .where(real, ExamAttempt.level == level, ExamAttempt.passed == 1)
    )

    base = max(onboarded, 1)
    lines = [
        f"📉 <b>Voronka — {level}</b>\n",
        f"1️⃣ Ro'yxatdan o'tgan: <b>{onboarded}</b> / {total} jami",
        f"2️⃣ Darsni boshlagan: <b>{started}</b>  {_bar(started/base)} {round(100*started/base)}%",
        f"3️⃣ {level} ni tugatgan: <b>{completed_all}</b>  {_bar(completed_all/base)} {round(100*completed_all/base)}%",
        f"4️⃣ Imtihon topshirgan: <b>{exam_finished}</b> · o'tgan: <b>{exam_passed}</b>",
    ]
    if exam_finished:
        lines.append(f"   Imtihon o'tish foizi: <b>{round(100*exam_passed/exam_finished)}%</b>")

    # Dars bo'yicha drop-off (faqat kimdir yetgan darslar)
    lines.append("\n📚 <b>Dars bo'yicha yetib borish</b>")
    peak = max(per_lesson.values()) or 1
    shown = 0
    for lid in lvl_ids:
        n = per_lesson[lid]
        if n == 0 and shown == 0:
            continue  # boshidagi 0 larni o'tkazmaymiz
        title = cur[lid]["title_uz"][:22]
        lines.append(f"<code>{lid}</code> {_bar(n/peak, 8)} {n} · {title}")
        shown += 1
        if shown >= 26:
            break

    return "\n".join(lines)


async def ratings_report(session: AsyncSession) -> str:
    """Dars baholari (👍/👎) va so'nggi fikrlar."""
    up = (
        await session.execute(
            select(func.count()).select_from(LessonRating).where(LessonRating.rating == 1)
        )
    ).scalar_one()
    down = (
        await session.execute(
            select(func.count()).select_from(LessonRating).where(LessonRating.rating == -1)
        )
    ).scalar_one()

    lines = [f"⭐ <b>Dars baholari</b>\n👍 {up} · 👎 {down}\n"]

    # Eng ko'p 👎 olgan darslar
    neg = (
        await session.execute(
            select(LessonRating.lesson_id, func.count())
            .where(LessonRating.rating == -1)
            .group_by(LessonRating.lesson_id)
            .order_by(func.count().desc())
            .limit(8)
        )
    ).all()
    if neg:
        lines.append("👎 <b>Ko'p shikoyat bo'lgan darslar</b>")
        for lid, cnt in neg:
            lines.append(f"<code>{lid}</code> · {cnt} 👎")

    # So'nggi fikrlar
    fb = (
        await session.execute(
            select(Feedback, User.name, User.tg_id)
            .join(User, User.id == Feedback.user_id)
            .order_by(Feedback.id.desc())
            .limit(8)
        )
    ).all()
    if fb:
        lines.append("\n💬 <b>So'nggi fikrlar</b>")
        for f, name, tg_id in fb:
            when = _local_date(f.created_at).isoformat()
            snippet = f.text[:120].replace("<", "&lt;").replace(">", "&gt;")
            lines.append(f"• <b>{name or tg_id}</b> ({when}): {snippet}")

    if up == down == 0 and not fb:
        return "Hozircha baho yoki fikr yo'q."
    return "\n".join(lines)


async def retention(session: AsyncSession, weeks: int = 6) -> str:
    """Kogorta retentsiyasi — D1/D7/D30 va haftalik kogortalar.

    Tashqi analitika xizmati kerak emas: ro'yxatdan o'tgan sana (users) va
    faollik kunlari (xp_log) allaqachon bazada. Faol kun = o'sha kuni XP
    olingan kun (dars, takror, imtihon — hammasi XP yozadi).
    """
    users = (
        await session.execute(
            select(User.id, User.created_at).where(User.is_demo == 0)
        )
    ).all()
    if not users:
        return "Hali foydalanuvchi yo'q."

    real_ids = {uid for uid, _ in users}
    xp_rows = (
        await session.execute(select(XpLog.user_id, XpLog.created_at))
    ).all()
    active: dict[int, set] = {}
    for uid, dt in xp_rows:
        if uid in real_ids:  # demo raqiblar hisobga olinmaydi
            active.setdefault(uid, set()).add(_local_date(dt))

    today = _today()

    def retained(uid: int, joined, day_from: int, day_to: int) -> bool:
        """[day_from, day_to] oynasida kamida bir kun faolmi."""
        j = _local_date(joined)
        days = active.get(uid, set())
        return any(
            (j + timedelta(days=n)) in days for n in range(day_from, day_to + 1)
        )

    lines = ["📈 <b>Retentsiya</b>\n"]

    # D1 / D7 / D30 — faqat yetarlicha ulg'aygan kogortalar
    for label, lo, hi, min_age in (
        ("D1", 1, 1, 1),
        ("D7", 7, 7, 7),
        ("D30", 30, 30, 30),
    ):
        pool = [
            (uid, cr) for uid, cr in users
            if (today - _local_date(cr)).days >= min_age
        ]
        if not pool:
            lines.append(f"{label}: — (kogorta hali yosh)")
            continue
        kept = sum(1 for uid, cr in pool if retained(uid, cr, lo, hi))
        frac = kept / len(pool)
        lines.append(
            f"{label}: {_bar(frac)} {round(frac * 100)}% ({kept}/{len(pool)})"
        )

    # Haftalik kogortalar — kim qachon qo'shildi va 7 kunda qaytdimi
    lines.append("\n🗓 <b>Haftalik kogortalar</b> (qo'shilgan → 7 kunda qaytgan)")
    buckets: dict[str, list] = {}
    for uid, cr in users:
        j = _local_date(cr)
        monday = j - timedelta(days=j.weekday())
        buckets.setdefault(monday.isoformat(), []).append((uid, cr))

    for wk in sorted(buckets)[-weeks:]:
        group = buckets[wk]
        mature = [
            (uid, cr) for uid, cr in group
            if (today - _local_date(cr)).days >= 7
        ]
        if not mature:
            lines.append(f"{wk}: {len(group)} ta yangi · (hali 7 kun to'lmagan)")
            continue
        kept = sum(1 for uid, cr in mature if retained(uid, cr, 1, 7))
        frac = kept / len(mature)
        lines.append(
            f"{wk}: {len(group):3d} ta · D1-7 {_bar(frac, 8)} {round(frac * 100)}%"
        )

    # Yopishqoqlik: DAU/MAU
    dau = sum(1 for uid in active if today in active[uid])
    mau = sum(
        1 for uid, days in active.items()
        if any((today - d).days <= 30 for d in days)
    )
    sticky = round(dau / mau * 100) if mau else 0
    lines.append(f"\n🔁 <b>Yopishqoqlik</b>: DAU {dau} / MAU {mau} = {sticky}%")

    return "\n".join(lines)


async def all_real_tg_ids(session: AsyncSession) -> list[int]:
    return list(
        (
            await session.execute(
                select(User.tg_id).where(User.is_demo == 0)
            )
        ).scalars()
    )


# ─────────────────── AI ustoz — sarf va holat (K17.3) ───────────────────


def _usd(x: float) -> str:
    return f"${x:.2f}" if x >= 0.01 or x == 0 else f"${x:.4f}"


async def tutor_report(session: AsyncSession) -> str:
    """`/ustoz` — Anthropic sarfi ($), foydalanish, VIP holati, ogohlantirishlar.

    Maqsad: kredit qachon tugashini oldindan ko'rish va VIP daromad/xarajat
    nisbatini bir qarashda bilish."""
    from config import settings
    from services import ai_usage, alerts, stt

    today = _today()
    now = utcnow()
    today_start = _day_start_utc(today)
    week_start = _day_start_utc(today - timedelta(days=6))
    month_start = _day_start_utc(today - timedelta(days=29))
    cal_month_start = _day_start_utc(today.replace(day=1))

    async def scalar(q):
        return (await session.execute(q)).scalar_one()

    # ── Anthropic sarfi ──
    u_today = await ai_usage.summary(session, today_start)
    u_week = await ai_usage.summary(session, week_start)
    u_month = await ai_usage.summary(session, month_start)
    u_all = await ai_usage.summary(session)
    per_call = u_month["cost"] / u_month["calls"] if u_month["calls"] else 0.0
    daily_avg = u_week["cost"] / 7
    by_feature = " · ".join(
        f"{ai_usage.FEATURES.get(f, f)} {v['calls']} ({_usd(v['cost'])})"
        for f, v in sorted(u_month["by"].items(), key=lambda kv: -kv[1]["cost"])
    ) or "—"
    # K23.4: model bo'yicha (30 kun) — VIP modeli sozlangan bo'lsa ulushi ko'rinsin
    models_line = " · ".join(
        f"{ai_usage.short_model(m) if m else 'Haiku 4.5'} {v['calls']} ({_usd(v['cost'])})"
        for m, v in sorted(u_month["by_model"].items(), key=lambda kv: -kv[1]["cost"])
    ) or ai_usage.short_model(settings.tutor_model)
    if settings.tutor_vip_model:
        models_line += f" · VIP: {ai_usage.short_model(settings.tutor_vip_model)}"
    tok = u_month["usage"]
    cache_share = (
        round(tok["cache_read"] / (tok["in"] + tok["cache_read"] + tok["cache_write"]) * 100)
        if (tok["in"] + tok["cache_read"] + tok["cache_write"])
        else 0
    )

    # ── Foydalanish (tutor_turns) ──
    async def turns(since):
        rows = (
            await session.execute(
                select(
                    TutorTurn.mode,
                    func.count(),
                    func.coalesce(func.sum(TutorTurn.voice), 0),
                )
                .where(TutorTurn.created_at >= since)
                .group_by(TutorTurn.mode)
            )
        ).all()
        d = {"chat": 0, "mock": 0, "voice": 0}
        total = 0
        for mode, n, voice in rows:
            d[mode if mode in d else "chat"] += n
            d["voice"] += voice
            total += n
        d["total"] = total
        d["users"] = await scalar(
            select(func.count(func.distinct(TutorTurn.user_id))).where(
                TutorTurn.created_at >= since
            )
        )
        return d

    t_today = await turns(today_start)
    t_week = await turns(week_start)
    voice_pct = round(t_week["voice"] / t_week["total"] * 100) if t_week["total"] else 0
    mocks_month, mock_avg = (
        await session.execute(
            select(func.count(), func.coalesce(func.avg(MockResult.score), 0)).where(
                MockResult.created_at >= month_start
            )
        )
    ).one()

    # ── VIP ──
    vip_active = await scalar(
        select(func.count()).select_from(User).where(User.vip_until > now)
    )
    vip_expiring = await scalar(
        select(func.count())
        .select_from(User)
        .where(User.vip_until > now, User.vip_until <= now + timedelta(days=3))
    )
    pending = await scalar(
        select(func.count()).select_from(PaymentRequest).where(PaymentRequest.status == "pending")
    )
    paid_n, paid_sum = (
        await session.execute(
            select(func.count(), func.coalesce(func.sum(PaymentRequest.amount), 0)).where(
                PaymentRequest.status == "approved",
                PaymentRequest.decided_at >= cal_month_start,
            )
        )
    ).one()

    auto_n = await scalar(
        select(func.count()).select_from(PaymentRequest).where(
            PaymentRequest.status == "approved",
            PaymentRequest.provider == "telegram",
            PaymentRequest.decided_at >= cal_month_start,
        )
    )
    paid_fmt = f"{paid_sum:,}".replace(",", " ")

    # ── Sifat halqasi: 👍/👎 ──
    async def rating(since):
        n, good = (
            await session.execute(
                select(func.count(), func.coalesce(func.sum(TutorRating.good), 0)).where(
                    TutorRating.created_at >= since
                )
            )
        ).one()
        return n, good

    r_n, r_good = await rating(month_start)
    w_n, w_good = await rating(week_start)
    bad_rows = (
        await session.execute(
            select(TutorRating.mode, TutorRating.topic, TutorRating.comment)
            .where(TutorRating.good == 0, TutorRating.created_at >= month_start)
            .order_by(TutorRating.id.desc())
            .limit(3)
        )
    ).all()
    if r_n:
        quality_line = (
            f"• Sifat (30 kun): 👍 <b>{round(r_good / r_n * 100)}%</b> ({r_n} baho)"
            + (f" · 7 kun: 👍 {round(w_good / w_n * 100)}% ({w_n})" if w_n else "")
        )
    else:
        quality_line = "• Sifat: hali baho yo'q"
    bad_lines = "".join(
        f"\n  👎 {m} · {t or '—'}" + (f": {c[:60]}" if c else "") for m, t, c in bad_rows
    )

    # ── Kalitlar va ogohlantirishlar ──
    ai_ok = "✅" if settings.anthropic_api_key else "❌ ANTHROPIC_API_KEY bo'sh"
    if not settings.stt_api_key:
        stt_state = "❌ STT_API_KEY bo'sh (mikrofon o'chiq)"
    elif stt.last_error == "auth":
        stt_state = "❌ kalit rad etildi (401) — Groq gsk_ kaliti kerak"
    elif stt.last_error == "rate":
        stt_state = "⚠️ Groq limiti (429) — Dev Tier yoqing"
    elif stt.last_error:
        stt_state = f"⚠️ oxirgi xato: {stt.last_error}"
    else:
        stt_state = "✅"
    st = stt.stats()
    stt_today = (
        f"{st['ok']} ok · {st['empty']} tushunilmadi · {st['rate']} limit(429) · {st['fail']} xato"
        + (f" · {st['retried']} qayta urinish" if st["retried"] else "")
    )
    if settings.stt_openai_api_key:
        oa = f"✅ {settings.stt_openai_model}" if not stt.openai_error else f"⚠️ xato «{stt.openai_error}» — Groq zaxira ishladi"
        stt_today += (
            f"\n• OpenAI STT: {oa} · bugun {st['openai']} ta · ~${st['openai_cost']:.2f}"
            + (f" · {st['fallback']} marta Groq'ga o'tildi" if st["fallback"] else "")
        )
    sent = alerts.last_sent()
    alert_line = (
        " · ".join(
            f"{k} {(v + TASHKENT_OFFSET):%d.%m %H:%M}" for k, v in sorted(sent.items())
        )
        or "yo'q"
    )

    return (
        "🎓 <b>AI ustoz — sarf va holat</b>\n\n"
        f"💰 <b>Anthropic sarfi</b> ({models_line})\n"
        f"• Bugun: <b>{u_today['calls']}</b> chaqiruv · <b>{_usd(u_today['cost'])}</b>\n"
        f"• 7 kun: {u_week['calls']} · {_usd(u_week['cost'])} "
        f"(kuniga o'rtacha {_usd(daily_avg)})\n"
        f"• 30 kun: {u_month['calls']} · {_usd(u_month['cost'])} "
        f"(chaqiruv o'rtacha {_usd(per_call)}, cache {cache_share}%)\n"
        f"• Jami: {u_all['calls']} · <b>{_usd(u_all['cost'])}</b>\n"
        f"• Prognoz: shu sur'atda oyiga ≈ <b>{_usd(daily_avg * 30)}</b>\n"
        f"• 30 kun bo'yicha: {by_feature}\n\n"
        "🗣 <b>Foydalanish</b>\n"
        f"• Bugun: <b>{t_today['total']}</b> javob (💬 {t_today['chat']} · 🎯 {t_today['mock']}) · "
        f"{t_today['users']} o'quvchi\n"
        f"• 7 kun: {t_week['total']} javob · {t_week['users']} o'quvchi · 🎤 ovozli {voice_pct}%\n"
        f"• Mock yakunlangan (30 kun): {mocks_month} · o'rtacha ball {round(mock_avg)}\n"
        f"• Limitlar: VIP {settings.tutor_daily_turns}/kun · bepul {settings.tutor_free_turns}/kun\n"
        f"{quality_line}{bad_lines}\n\n"
        "👑 <b>VIP</b>\n"
        f"• Faol: <b>{vip_active}</b> · 3 kun ichida tugaydi: {vip_expiring}\n"
        f"• Kutayotgan cheklar: <b>{pending}</b>\n"
        f"• Bu oy tasdiqlangan: {paid_n} ta ({auto_n} avto) · <b>{paid_fmt}</b> so'm\n"
        "• To'lov usuli: chek (kartaga o'tkazma + skrinshot)\n\n"
        "🔑 <b>Xizmatlar</b>\n"
        f"• Anthropic: {ai_ok}\n"
        f"• Ovoz (STT): {stt_state}\n"
        f"• STT bugun: {stt_today}\n"
        f"• Ogohlantirishlar: {alert_line}\n\n"
        "ℹ️ /payments /vip"
    )

