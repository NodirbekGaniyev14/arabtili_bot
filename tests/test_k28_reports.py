"""K28 xabarlari (#F126–#F135): yasalgan savollarda ikkinchi to'g'ri variant yo'q, xato variant izohi,
imtihon «i'rob» savoli, ustoz 👎 xabari."""

import json
from pathlib import Path

import pytest

from services.curriculum import load_curriculum, load_lesson_v2, written_lesson_ids
from services.lesson_test import _level_vocab, build_test, generated_bank, same_word

ROOT = Path(__file__).resolve().parent.parent
Q_AR_UZ = ("Bu so'z nima degani?", "Tarjimasi qaysi?", "Bu yasalma nima degani?")


def _pairs(lid: str, meta: dict) -> list[tuple[str, str]]:
    data = load_lesson_v2(lid) or {}
    pairs = list(_level_vocab(meta["level"]))
    pairs += [(v.get("ar", ""), v.get("uz", "")) for v in data.get("vocabulary", [])]
    for r in (data.get("grammar") or {}).get("table") or []:
        pairs.append((str(r.get("ar", "")), str(r.get("uz", ""))))
    for r in data.get("roots", []):
        pairs += [(str(d.get("ar", "")), str(d.get("uz", ""))) for d in r.get("derived", [])]
    return [(a.strip(), u.strip()) for a, u in pairs if a and u]


def test_no_second_correct_option_in_generated_mcq():
    """تَكْتُبُ: «u (ayol) yozadi» ham, «sen yozasan» ham to'g'ri edi; A0 harf tavsiflari ikki xil — endi yo'q."""
    cur, written = load_curriculum(), written_lesson_ids()
    bad = []
    for lid, meta in sorted(cur.items()):
        if meta["type"] != "lesson" or lid not in written:
            continue
        pairs = _pairs(lid, meta)
        for it in generated_bank(lid):
            others = [o for o in it["options"] if o != it["answer"]]
            if it["q_uz"] in Q_AR_UZ:
                bad += [(lid, it["q_ar"], o) for o in others if any(u == o and same_word(a, it["q_ar"]) for a, u in pairs)]
            elif it["q_uz"].endswith("— qaysi so'z?"):
                uz = it["q_uz"][1:].rsplit("» — qaysi so'z?", 1)[0]
                bad += [(lid, uz, o) for o in others if same_word(o, it["answer"]) or any(same_word(a, o) and u == uz for a, u in pairs)]
            elif it["q_uz"] == "Eshiting va so'zni toping":
                bad += [(lid, it["answer"], o) for o in others if same_word(o, it["answer"])]
    assert not bad, bad[:10]


def test_wrong_option_notes():
    """#F135: كِتَابَة ni «u (ayol) yozdi» deb tanlagan o'quvchi — «= كَتَبَتْ» izohini ko'radi."""
    items = [it for a in range(4) for it in build_test("a2-19", a)["items"]]
    noted = [it for it in items if it.get("option_notes")]
    assert noted
    for it in noted:
        assert it["answer"] not in it["option_notes"]
        assert set(it["option_notes"]) <= set(it["options"])
    assert same_word("ب", "بَ") and not same_word("كَتَبْتُ", "كَتَبَتْ"), "harakatli ikki shakl — atayin distraktor"


def test_exam_irab_question_is_a_meaning():
    """#F131: «Eshitgan so'z ma'nosi?» — javob faqat «i'rob» (so'zning o'zi) edi."""
    pool = json.loads((ROOT / "content" / "exams" / "b2_pool.json").read_text(encoding="utf-8"))
    it = next(q for q in pool["listening"] if q.get("audio") == "b2/irab.mp3")
    assert it["answer"] in it["options"] and "—" in it["answer"] and len(set(it["options"])) == 4


@pytest.mark.asyncio
async def test_tutor_rate_alert_rtl_name_and_daily(session, make_user, monkeypatch):
    """Ustoz 👎: arabcha ism qatorni teskari aylantirmasin (LRM), kunlik savolda «0 javob» yo'q."""
    import httpx

    from db.session import get_session
    from main import app
    from services.telegram_auth import get_current_user

    class Bot:
        def __init__(self):
            self.sent = []

        async def send_message(self, chat, text, **kw):
            self.sent.append(text)

    from config import settings

    monkeypatch.setattr(settings, "admin_id", 1)
    u = await make_user('م"', username="MubinaB2")

    async def _session():
        yield session

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: u
    bot = Bot()
    app.state.bot = bot
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            r = await c.post("/api/v2/tutor/rate", json={"session_key": "daily-abc12345", "mode": "daily", "topic": "a2-08", "good": False})
            assert r.status_code == 200, r.text
    finally:
        app.dependency_overrides.clear()
        del app.state.bot
    assert bot.sent and "‎" in bot.sent[0] and "javob" not in bot.sent[0]


# ── #F138: «Savol tushunarsiz» — a2-08 «mendan so'radi» ──


def test_authored_option_notes_reach_the_learner():
    """Muallif yozgan izohlar mikro-testga o'tadi: xato variant (سَأَلِي) tanlansa — nega xato ekani ko'rinadi."""
    items = [it for a in range(8) for it in build_test("a2-08", a)["items"]]
    it = next(i for i in items if i["answer"] == "سَأَلَنِي")
    assert "arabchasi qaysi" in it["q_uz"] and "himoya nuni" in it["explain_uz"]
    notes = it["option_notes"]
    assert set(notes) == {"سَأَلِي", "سَأَلَنَا", "سَأَلَهُ"} and it["answer"] not in notes
    assert "nun" in notes["سَأَلِي"] and "biz" in notes["سَأَلَنَا"]


def test_option_notes_schema_rules():
    from services.lesson_schema import LessonV2, validate_lesson

    raw = json.loads((ROOT / "content" / "modules" / "a2" / "a2-08.json").read_text(encoding="utf-8"))
    errs, _ = validate_lesson(LessonV2.model_validate(raw))
    assert not [e for e in errs if "option_notes" in e], errs

    bad = json.loads(json.dumps(raw))
    mcq = next(t for t in bad["micro_test"] if t["type"] == "mcq" and t["answer"] == "سَأَلَنِي")
    mcq["option_notes"]["سَأَلَنِي"] = "javobning o'ziga izoh yozib bo'lmaydi"
    mcq["option_notes"]["yo'q variant"] = "variantlar ichida emas"
    mcq["option_notes"]["سَأَلَهُ"] = "  "
    tr = next(t for t in bad["micro_test"] if t["type"] == "translate_uz_ar")
    tr["option_notes"] = {"x": "faqat mcq"}
    errs, _ = validate_lesson(LessonV2.model_validate(bad))
    joined = "\n".join(errs)
    assert joined.count("option_notes") >= 4, joined


@pytest.mark.asyncio
async def test_admin_notice_rtl_name(session, make_user):
    """Admin xabari: arabcha ism (أمر الدين) qatorni teskari aylantirmasin — LRM; «...» ism → @username."""
    from services import feedback as fs

    u = await make_user("أمر الدين", username="")
    fb = await fs.save(session, u.id, "Tur: x", source="issue", context="a2-08")
    head = fs.admin_notice(fb, u).splitlines()[1]
    assert head.startswith("أمر الدين‎, —, ID ") and head.endswith("a2-08"), head

    u2 = await make_user("...", username="ali")
    fb2 = await fs.save(session, u2.id, "Tur: y", source="issue", context="")
    assert fs.admin_notice(fb2, u2).splitlines()[1].startswith("@ali‎, @ali, ID ")
