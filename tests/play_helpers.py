"""Testlar uchun: dars/nazorat/zaif so'zlar urinishini «o'ynash» (K33.2 — javoblar serverda qulflanadi)."""

import json

from sqlalchemy import select

from db.models import QuizRun


async def run_items(session, run_id: int) -> list[dict]:
    """Urinishning TO'LIQ savollari (to'g'ri javobi bilan) — faqat bazadan; mijozga bunday ko'rinish bormaydi."""
    run = (await session.execute(select(QuizRun).where(QuizRun.id == run_id))).scalar_one()
    return json.loads(run.items_json)["items"]


async def answer_run(c, session, run_id: int, n_correct: int | None = None) -> list[dict]:
    """Savollarga javob beradi: dastlabki `n_correct` tasiga TO'G'RI, qolganiga noto'g'ri (None — hammasi to'g'ri).
    Har javob qaytargan ma'lumotni (reveal) ro'yxat qilib qaytaradi."""
    out = []
    for i, it in enumerate(await run_items(session, run_id)):
        good = n_correct is None or i < n_correct
        if it["type"] == "shadowing":
            given = "done" if good else ""
        else:
            given = it["answer"] if good else "zzz qqq"
        if not given:
            continue  # javobsiz qoldi
        r = await c.post(f"/api/v2/run/{run_id}/answer", json={"index": i, "given": given})
        assert r.status_code == 200, r.text
        out.append(r.json())
    return out


async def play_lesson(c, session, lesson_id: str, n_correct: int | None = None) -> dict:
    """Darsni ochadi (v=2), savollarga javob beradi va tugatadi. Dars natijasi JSON'i qaytadi."""
    r = await c.get(f"/api/v2/lessons/{lesson_id}?v=2")
    assert r.status_code == 200, r.text
    run_id = r.json()["run"]["id"]
    await answer_run(c, session, run_id, n_correct)
    r = await c.post(f"/api/v2/lessons/{lesson_id}/complete", json={"run_id": run_id})
    assert r.status_code == 200, r.text
    return r.json()
