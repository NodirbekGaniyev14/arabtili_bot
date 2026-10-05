"""Voronka (/funnel) — daraja bo'yicha drop-off va dars ICHIDA qayerda to'xtashadi (K32, 2026-10-05).

Egasi yuborgan A0 voronkasida eski hisobot (`admin.funnel`) xatolari:
- yiqilgan urinishlar (Progress.passed=0) ham «yetib borgan» sanalardi;
- «Imtihon topshirgan 184» > «A0 ni tugatgan 97»: `kind` filtri yo'q edi — mini-imtihonlar (25/50/75%) ham sanalgan;
- ro'yxat 26-darsda kesilardi (A0 — 41 dars);
- har dars alohida sanalardi, tartib buzilardi (a0-04 274 > a0-03 256) — endi «eng uzoq o'tgan darsi» bo'yicha;
- hamma davr aralash edi: K22.1 (2026-09-21, onboarding'dan darhol dars) ta'siri ko'rinmasdi — endi
  `/funnel A0 14` (oxirgi N kunda ro'yxatdan o'tganlar).

Dars ichi: `lesson_visits` — dars ochilishi (server, GET dars) va eng uzoq faza (LessonPlayerV2 yuboradi).

K32.1 (egasining birinchi natijasi): 1229 ro'yxatdan o'tgandan atigi 371 tasi A0 dan boshlagan, oxirgi 14 kunda
101 dan 26 tasi — ko'pchilik daraja testidan keyin A1+ dan boshlaydi, A0 voronkasi ularni ko'rsatmaydi. Endi `/funnel`
(argumentsiz) — boshlash darajasi bo'yicha umumiy ko'rinish. A0 imtihonini yuqori darajadagilar ham topshiradi (pastki
darajalar imtihoni doim ochiq — sertifikat uchun): ular «shu darajani o'qiganlar» dan alohida sanaladi.
"""

import html
import re
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ExamAttempt, LessonVisit, Plan, Progress, User, utcnow
from services.curriculum import load_curriculum, load_lesson_v2
from services.stats import TASHKENT_OFFSET

# LessonPlayerV2 fazalari (frontend nomlari bilan bir xil); «result» — natija ekrani
PHASE_LABEL = {
    "hook": "kirish",
    "grammar": "qoida",
    "roots": "o'zaklar",
    "vocab": "kartalar",
    "hejazi": "sheva",
    "reading": "o'qish",
    "listening": "tinglash",
    "speaking": "gapirish",
    "writing": "yozish",
    "passage": "matn",
    "test": "mikro-test",
    "result": "natija",
}
PHASE_NAMES = tuple(PHASE_LABEL)
MAX_DAYS = 365
MIN_DROP_BASE = 10  # kichik sonlarda foiz shovqin — tushish belgisi qo'yilmaydi
TOP_DROPS = 3
TG_LIMIT = 3900  # Telegram xabari 4096 belgi — sarlavhalarsiz qisqa variantga o'tiladi
USAGE = (
    "Foydalanish: <code>/funnel</code> (boshlash darajalari) · <code>/funnel 14</code> (oxirgi 14 kunda kelganlar) · "
    "<code>/funnel A0 14</code> (daraja darslari) · <code>/funnel a0-01</code> (dars ichida qayerda to'xtashadi)"
)
LEVELS = ("A0", "A1", "A2", "B1", "B2")
LESSON_ID = re.compile(r"[a-z]\d-\d{2}")


def lesson_phases(lesson_id: str) -> list[str]:
    """LessonPlayerV2 `phases` ro'yxatining serverdagi nusxasi + oxirida «result».
    Indekslar frontend yuboradigan `idx` bilan mos (vocab — har karta alohida faza)."""
    from services.reading import passage_for

    data = load_lesson_v2(lesson_id) or {}
    out = ["hook"]
    if (data.get("grammar") or {}).get("point_ar"):
        out.append("grammar")
    if data.get("roots"):
        out.append("roots")
    out += ["vocab"] * len(data.get("vocabulary") or [])
    if data.get("hejazi"):
        out.append("hejazi")
    skills = data.get("skills") or {}
    for name, field in (("reading", "text_ar"), ("listening", "audio"), ("speaking", "task_uz"), ("writing", "task_uz")):
        if (skills.get(name) or {}).get(field):
            out.append(name)
    if (passage_for(lesson_id) or {}).get("text_ar"):
        out.append("passage")
    return out + ["test", "result"]


# ── Yozish (dars API) ──


async def _visit(session: AsyncSession, user_id: int, lesson_id: str) -> LessonVisit | None:
    return (
        await session.execute(
            select(LessonVisit).where(LessonVisit.user_id == user_id, LessonVisit.lesson_id == lesson_id)
        )
    ).scalar_one_or_none()


async def _commit(session: AsyncSession) -> None:
    try:
        await session.commit()
    except IntegrityError:  # bir vaqtda ikki so'rov — birinchisi yozib bo'lgan, shu yetarli
        await session.rollback()


async def record_open(session: AsyncSession, user_id: int, lesson_id: str) -> None:
    """Dars ochildi (GET /api/v2/lessons/{id}); qayta ochish — opens+1."""
    visit = await _visit(session, user_id, lesson_id)
    now = utcnow()
    if visit is None:
        session.add(LessonVisit(user_id=user_id, lesson_id=lesson_id, opened_at=now, updated_at=now))
    else:
        visit.opens = (visit.opens or 0) + 1
        visit.updated_at = now
    await _commit(session)


async def record_phase(session: AsyncSession, user_id: int, lesson_id: str, idx: int, phase: str) -> None:
    """Dars ichidagi eng uzoq faza — faqat oshadi (qayta urinish yoki orqaga qaytish kamaytirmaydi)."""
    visit = await _visit(session, user_id, lesson_id)
    now = utcnow()
    if visit is None:
        session.add(LessonVisit(user_id=user_id, lesson_id=lesson_id, max_idx=idx, max_phase=phase,
                                opened_at=now, updated_at=now))
    elif idx > (visit.max_idx or 0):
        visit.max_idx, visit.max_phase, visit.updated_at = idx, phase, now
    else:
        return
    await _commit(session)


# ── Hisobot (admin /funnel) ──


def _bar(frac: float, width: int = 8) -> str:
    filled = round(max(0.0, min(1.0, frac)) * width)
    return "█" * filled + "░" * (width - filled)


def _pct(a: int, b: int) -> int:
    return round(100 * a / b) if b else 0


def _drops(counts: list[int]) -> dict[int, int]:
    """Indeks → oldingisiga nisbatan tushish foizi (oldingisi MIN_DROP_BASE dan kichik bo'lsa — yo'q)."""
    return {
        i: round(100 * (counts[i - 1] - counts[i]) / counts[i - 1])
        for i in range(1, len(counts))
        if counts[i - 1] >= MIN_DROP_BASE and counts[i] < counts[i - 1]
    }


def _top(drops: dict[int, int]) -> list[int]:
    return [i for i, d in sorted(drops.items(), key=lambda x: (-x[1], x[0]))[:TOP_DROPS] if d > 0]


def _period(days: int | None) -> str:
    return f"oxirgi {days} kunda kelganlar" if days else "hamma vaqt"


def parse_args(tokens: list[str]) -> tuple[str, int | None]:
    """`/funnel [A0|a0-01] [kun]` → (nishon, kun); nishonsiz — umumiy ko'rinish."""
    target, days = "", None
    for t in tokens:
        if t.isdigit():
            days = max(1, min(int(t), MAX_DAYS))
        elif t.strip():
            target = t.strip()
    return target, days


async def report(session: AsyncSession, target: str = "", days: int | None = None) -> str:
    if not target:
        return await overview(session, days)
    if LESSON_ID.fullmatch(target.lower()):
        return await lesson_report(session, target.lower(), days)
    return await level_report(session, target.upper(), days)


async def overview(session: AsyncSession, days: int | None = None) -> str:
    """Boshlash darajasi (daraja testi natijasi) bo'yicha: nechta kishi va birinchi darslar natijasi."""
    cur = load_curriculum()
    since = utcnow() - timedelta(days=days) if days else None
    real = [User.is_demo == 0] + ([User.created_at >= since] if since else [])

    total = (await session.execute(select(func.count()).select_from(User).where(*real))).scalar_one()
    latest = select(func.max(Plan.id).label("pid")).group_by(Plan.user_id).subquery()
    plans = (
        await session.execute(
            select(Plan.user_id, Plan.start_lesson, Plan.level)
            .join(latest, Plan.id == latest.c.pid)
            .join(User, User.id == Plan.user_id)
            .where(*real)
        )
    ).all()
    start = {uid: (cur[s]["level"] if s in cur else (lvl or "A0")) for uid, s, lvl in plans}
    passed_n = dict(
        (
            await session.execute(
                select(Progress.user_id, func.count(func.distinct(Progress.lesson_id)))
                .join(User, User.id == Progress.user_id)
                .where(*real, Progress.passed == 1)
                .group_by(Progress.user_id)
            )
        ).all()
    )
    tried = set(
        (
            await session.execute(
                select(Progress.user_id).join(User, User.id == Progress.user_id).where(*real).distinct()
            )
        ).scalars().all()
    )

    everyone = max(len(plans), 1)
    lines = [
        f"🧭 <b>Voronka — qaysi darajadan boshlashadi</b> · {_period(days)}\n",
        f"👤 Ro'yxatdan o'tgan (reja bor): <b>{len(plans)}</b> / {total}",
    ]
    for lvl in LEVELS:
        users = [uid for uid, s in start.items() if s == lvl]
        if not users:
            continue
        n = len(users)
        one = sum(1 for uid in users if passed_n.get(uid, 0) >= 1)
        five = sum(1 for uid in users if passed_n.get(uid, 0) >= 5)
        failed = sum(1 for uid in users if uid in tried and not passed_n.get(uid))
        lines += [
            f"\n<b>{lvl}</b> dan · <b>{n}</b> kishi ({_pct(n, everyone)}%)  {_bar(n / everyone)}",
            f"   ✅ 1+ dars {_pct(one, n)}% · 5+ dars {_pct(five, n)}% · ❌ faqat yiqilgan {_pct(failed, n)}%"
            f" · 💤 testgacha yetmagan {_pct(n - one - failed, n)}%",
        ]
    lines += [
        "",
        "<i>✅ kamida 1 dars o'tgan (≥60%) · ❌ dars testidan o'tolmagan, boshqa dars ham yo'q · "
        "💤 birorta dars testigacha yetmagan</i>",
        f"🔍 Batafsil: <code>/funnel A1{' ' + str(days) if days else ''}</code> · dars ichida: <code>/funnel a1-01</code>",
    ]
    return "\n".join(lines)


async def level_report(session: AsyncSession, level: str = "A0", days: int | None = None) -> str:
    cur = load_curriculum()
    ids = sorted(
        (lid for lid, m in cur.items() if m["level"] == level and m["type"] == "lesson"),
        key=lambda x: cur[x]["order"],
    )
    if not ids:
        return f"«{html.escape(level, quote=False)}» darajasi topilmadi.\n{USAGE}"
    pos = {lid: i for i, lid in enumerate(ids)}
    since = utcnow() - timedelta(days=days) if days else None
    real = [User.is_demo == 0] + ([User.created_at >= since] if since else [])

    total = (await session.execute(select(func.count()).select_from(User).where(*real))).scalar_one()
    latest = select(func.max(Plan.id).label("pid")).group_by(Plan.user_id).subquery()
    plans = (
        await session.execute(
            select(Plan.user_id, Plan.start_lesson, User.created_at)
            .join(latest, Plan.id == latest.c.pid)
            .join(User, User.id == Plan.user_id)
            .where(*real)
        )
    ).all()
    here = {uid for uid, start, _ in plans if start in pos}

    # Faqat O'TILGAN darslar (≥60%); «eng uzoq o'tgan darsi» — ketma-ketlik buzilmaydi
    rows = (
        await session.execute(
            select(Progress.user_id, Progress.lesson_id)
            .join(User, User.id == Progress.user_id)
            .where(*real, Progress.passed == 1, Progress.lesson_id.in_(ids))
            .distinct()
        )
    ).all()
    furthest: dict[int, int] = {}
    passed: dict[int, set[str]] = {}
    for uid, lid in rows:
        furthest[uid] = max(furthest.get(uid, -1), pos[lid])
        passed.setdefault(uid, set()).add(lid)
    base = max(len(here | set(furthest)), 1)
    completed = sum(1 for s in passed.values() if len(s) == len(ids))

    # Imtihon: pastki darajalar imtihoni yuqori darajadagilarga doim ochiq (sertifikat) — ular alohida
    exams = (
        await session.execute(
            select(ExamAttempt.user_id, ExamAttempt.passed, ExamAttempt.finished_at)
            .join(User, User.id == ExamAttempt.user_id)
            .where(*real, ExamAttempt.kind == "level", ExamAttempt.level == level)
        )
    ).all()
    learners = here | set(furthest)
    took = {uid for uid, _, done in exams if done is not None}
    exam_done = len(took & learners)
    exam_ok = len({uid for uid, ok, _ in exams if ok == 1} & learners)
    exam_other = len(took - learners)

    head = [
        f"📉 <b>Voronka — {level}</b> · {_period(days)}\n",
        f"👤 Ro'yxatdan o'tgan (reja bor): <b>{len(plans)}</b> / {total} · {level} dan boshlagan: <b>{len(here)}</b>",
    ]
    # Dars ochilishi — kuzatuv boshlangandan keyin kelganlar uchungina aniq
    track_from = (await session.execute(select(func.min(LessonVisit.opened_at)))).scalar()
    if track_from:
        fresh = {uid for uid, start, created in plans if start in pos and created and created >= track_from}
        if fresh:
            visited = set(
                (
                    await session.execute(
                        select(LessonVisit.user_id).where(LessonVisit.lesson_id.in_(ids)).distinct()
                    )
                ).scalars().all()
            )
            opened = len(fresh & visited)
            ok = len(fresh & set(furthest))
            head.append(
                f"👀 {track_from + TASHKENT_OFFSET:%d.%m} dan kelgan {len(fresh)} kishi: darsni ochgan <b>{opened}</b> "
                f"({_pct(opened, len(fresh))}%) · 1 dars o'tgan <b>{ok}</b> ({_pct(ok, len(fresh))}%)"
            )
    head += [
        f"✅ Kamida 1 dars o'tgan: <b>{len(furthest)}</b>  {_bar(len(furthest) / base, 10)} {_pct(len(furthest), base)}%",
        f"🏁 {level} ni tugatgan ({len(ids)} dars): <b>{completed}</b>  {_bar(completed / base, 10)} {_pct(completed, base)}%",
        f"🎓 {level} imtihoni (shu darajani o'qiganlar): topshirgan <b>{exam_done}</b> · o'tgan <b>{exam_ok}</b>"
        + (f" ({_pct(exam_ok, exam_done)}%)" if exam_done else "")
        + (f"\n   + yuqori darajadan boshlaganlar (darssiz, sertifikat uchun): {exam_other}" if exam_other else ""),
    ]

    reach = [sum(1 for f in furthest.values() if f >= i) for i in range(len(ids))]
    drops = _drops(reach)
    top = _top(drops)
    peak = max(reach[0], 1)

    def lesson_lines(titles: bool) -> list[str]:
        out = []
        for i, lid in enumerate(ids):
            drop = f" −{drops[i]}%" if drops.get(i) else ""
            mark = "🔻" if i in top else ""
            title = f" · {html.escape(cur[lid]['title_uz'][:18], quote=False)}" if titles else ""
            out.append(f"<code>{lid}</code> {_bar(reach[i] / peak)} {reach[i]}{drop}{mark}{title}")
        return out

    tail = ["\n📚 <b>Darslar</b> — shu darsgacha (kamida) o'tganlar, −% — oldingi darsga nisbatan"]
    foot = []
    if top:
        foot.append("\n🔻 Eng katta tushish: " + ", ".join(f"{ids[i]} (−{drops[i]}%)" for i in top))
    foot.append(f"🔍 Dars ichida qayerda to'xtashadi: <code>/funnel {ids[0]}</code> · davr: <code>/funnel {level} 14</code>")

    text = "\n".join(head + tail + lesson_lines(True) + foot)
    if len(text) > TG_LIMIT:
        text = "\n".join(head + tail + lesson_lines(False) + foot)
    return text


async def lesson_report(session: AsyncSession, lesson_id: str, days: int | None = None) -> str:
    meta = load_curriculum().get(lesson_id)
    if not meta or meta["type"] != "lesson":
        return f"«{html.escape(lesson_id, quote=False)}» darsi topilmadi.\n{USAGE}"
    phases = lesson_phases(lesson_id)
    since = utcnow() - timedelta(days=days) if days else None
    cond = [LessonVisit.lesson_id == lesson_id, User.is_demo == 0] + ([LessonVisit.opened_at >= since] if since else [])
    title = f"🔍 <b>{lesson_id} ichida</b> · {html.escape(meta['title_uz'], quote=False)} · {'oxirgi ' + str(days) + ' kun' if days else 'hamma vaqt'}"

    visits = (
        await session.execute(
            select(LessonVisit.max_idx, LessonVisit.opens).join(User, User.id == LessonVisit.user_id).where(*cond)
        )
    ).all()
    if not visits:
        return f"{title}\n\nHali ma'lumot yo'q — kuzatuv shu yangilanishdan keyin boshlanadi (o'quvchi darsni ochganda yoziladi)."

    # Bir xil nomli fazalar (har lug'at kartasi) — bitta bosqich: birinchi indeksidan boshlab
    stages: list[tuple[str, int]] = []
    for i, name in enumerate(phases):
        if name not in (s for s, _ in stages):
            stages.append((name, i))
    last = len(phases) - 1

    def stage_of(idx: int) -> int:
        return max(k for k, (_, first) in enumerate(stages) if first <= min(max(idx, 0), last))

    at = [stage_of(v.max_idx) for v in visits]
    reach = [sum(1 for s in at if s >= k) for k in range(len(stages))]
    stopped = [sum(1 for s in at if s == k) for k in range(len(stages))]
    passed = (
        await session.execute(
            select(func.count(func.distinct(Progress.user_id)))
            .select_from(Progress)
            .join(LessonVisit, (LessonVisit.user_id == Progress.user_id) & (LessonVisit.lesson_id == Progress.lesson_id))
            .join(User, User.id == Progress.user_id)
            .where(*cond, Progress.lesson_id == lesson_id, Progress.passed == 1)
        )
    ).scalar_one()

    opened = len(visits)
    opens = sum(v.opens or 1 for v in visits)
    rows = []
    for k, (name, _) in enumerate(stages):
        stop = f" · to'xtagan {stopped[k]}" if stopped[k] and name != "result" else ""
        rows.append(f"{PHASE_LABEL.get(name, name):<10} {_bar(reach[k] / opened)} {reach[k]:>4}{stop}")
    worst = sorted(
        ((stopped[k], name) for k, (name, _) in enumerate(stages) if name != "result" and stopped[k]), reverse=True
    )[:TOP_DROPS]
    lines = [
        title,
        "",
        f"Ochgan: <b>{opened}</b> kishi (jami {opens} marta) · o'tgan (≥60%): <b>{passed}</b> ({_pct(passed, opened)}%)",
        "<pre>" + html.escape("\n".join(rows), quote=False) + "</pre>",
    ]
    if worst:
        lines.append(
            "🔻 Ko'p to'xtagan joy: "
            + ", ".join(f"{PHASE_LABEL.get(n, n)} — {c} ({_pct(c, opened)}%)" for c, n in worst)
        )
    lines.append("<i>«to'xtagan» — shu bosqichdan nariga o'tmagan (darsni yopgan yoki hali davom ettirmagan)</i>")
    return "\n".join(lines)
