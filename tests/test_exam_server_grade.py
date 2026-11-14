"""K33 — imtihon ballini SERVER hisoblaydi: javobsiz savollar, mijoz javoblari, soxta ball urinishlari."""

import json
import random
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select

from db.models import AnswerLog, ExamAttempt, Plan, XpLog
from services import exam as ex

ROOT = Path(__file__).resolve().parent.parent
RUNNER = ROOT / "tests" / "js" / "answer_check_runner.cjs"
ESBUILD = ROOT / "webapp" / "node_modules" / "esbuild"
LEVELS = ["A0", "A1", "A2", "B1", "B2"]

# Mijozga hech qachon bormasligi kerak bo'lgan kalitlar (rekursiv)
SECRET_KEYS = {"answer", "explain_uz", "option_notes", "accept", "root", "pattern", "words"}


def _keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _keys(v)


def _all_items(exam: dict):
    for sec in ("reading", "listening"):
        yield from exam[sec]
    for p in exam.get("passages") or []:
        yield from p["questions"]


# ── Pool butunligi: har savolni server baholay oladi ──


@pytest.mark.parametrize("level", LEVELS)
def test_pool_items_are_gradable(level):
    pool = ex.load_pool(level)
    items = list(_all_items(pool))
    assert items
    for it in items:
        if it.get("options"):
            assert it["answer"] in it["options"], it
            assert len(set(it["options"])) == len(it["options"]), it
        else:
            assert it["type"] in ("dictation", "match_root"), f"baholab bo'lmaydigan savol: {it}"


# ── Mijozga javob oshkor bo'lmaydi ──


@pytest.mark.parametrize("level", LEVELS)
def test_public_exam_has_no_answers(level):
    exam = ex.build_exam(level)
    pub = ex.public_exam(exam)
    assert not SECRET_KEYS & set(_keys(pub)), SECRET_KEYS & set(_keys(pub))
    # savollar tartibi va soni saqlanadi (mijoz javoblari indeks bo'yicha taqqoslanadi)
    assert [i["q_uz"] for i in pub["reading"]] == [i["q_uz"] for i in exam["reading"]]
    assert len(pub["listening"]) == len(exam["listening"])
    assert len(pub["passages"]) == len(exam["passages"])
    for src, out in zip(_all_items(exam), _all_items(pub)):
        if src.get("options") or src["type"] == "match_root":
            assert src["answer"] in out["options"], "to'g'ri javob variantlar orasida bo'lishi shart"
        else:
            assert out["options"] == []


def test_public_options_are_shuffled_not_answer_first():
    """Poolda birinchi variant har doim to'g'ri javob — mijozga shu tartibda bermaslik kerak."""
    exam = ex.build_exam("A1")
    rnd = random.Random(7)
    firsts = [
        out["options"][0] == src["answer"]
        for src, out in zip(_all_items(exam), _all_items(ex.public_exam(exam, rnd)))
    ]
    assert len(firsts) >= 16
    assert sum(firsts) < len(firsts) * 0.6


def test_match_root_gets_server_built_options():
    item = {"type": "match_root", "q_uz": "o'zak", "q_ar": "مَكْتَب", "answer": "ك ت ب", "root": "ك ت ب"}
    exam = {"level": "A0", "minutes": 30, "reading": [item], "listening": [], "writing": [], "speaking": []}
    out = ex.public_exam(exam)["reading"][0]
    assert len(out["options"]) == 4 and len(set(out["options"])) == 4
    assert "ك ت ب" in out["options"]


# ── Savol baholash ──


def _mcq():
    return {"type": "mcq", "q_uz": "q", "options": ["a", "b", "c", "d"], "answer": "a"}


def test_check_item_options_exact_match():
    assert ex.check_item(_mcq(), "a")
    assert ex.check_item(_mcq(), " a ")
    assert not ex.check_item(_mcq(), "b")
    assert not ex.check_item(_mcq(), "")
    assert not ex.check_item(_mcq(), "A")


def test_check_item_unknown_shape_is_wrong():
    assert not ex.check_item({"type": "fill_blank", "answer": "x"}, "x")


def test_check_item_dictation():
    it = {"type": "dictation", "q_uz": "yozing", "answer": "بَاب"}
    assert ex.check_item(it, "باب")
    assert ex.check_item(it, "بَاب")
    assert not ex.check_item(it, "بيت")
    assert not ex.check_item(it, "")
    ya = {"type": "dictation", "answer": "مَاء"}
    assert ex.check_item(ya, "ماء")
    assert ex.check_item({"type": "dictation", "answer": "مَتى"}, "متي")  # ى/ي kechiriladi
    assert ex.check_item({"type": "dictation", "answer": "تَعَلُّم"}, "تعللم")  # shadda o'rniga qo'sh harf
    assert ex.check_item({"type": "dictation", "answer": "x", "accept": ["مِيم"]}, "ميم")


# ── grade_answers ──


def _exam(n_r=4, n_l=4, n_w=2, n_s=3, passages=None):
    return {
        "level": "A0",
        "minutes": 30,
        "reading": [_mcq() for _ in range(n_r)],
        "listening": [_mcq() for _ in range(n_l)],
        "writing": [{"task_uz": "t"}] * n_w,
        "speaking": [{"q_ar": "x", "audio": "y"}] * n_s,
        "passages": passages or [],
    }


def test_grade_answers_counts_correct_only():
    c = ex.grade_answers(_exam(), ["a", "a", "b", ""], ["a", "a", "a", "a"], None, ["salom", "yozdim"], 3)
    assert c["reading_correct"] == 2
    assert c["listening_correct"] == 4
    assert c["writing_score"] == 100 and c["speaking_score"] == 100


def test_grade_answers_ignores_extra_and_missing():
    c = ex.grade_answers(_exam(n_r=2), ["a"] * 50, [], None, None, 99)
    assert c["reading_correct"] == 2, "ortiqcha javoblar sanalmaydi"
    assert c["listening_correct"] == 0
    assert c["writing_score"] == 0
    assert c["speaking_score"] == 100, "speaking_done savollar soniga qisiladi"


def test_writing_needs_real_text():
    c = ex.grade_answers(_exam(), [], [], None, ["ab", "   x   "], 0)
    assert c["writing_score"] == 0
    c = ex.grade_answers(_exam(), [], [], None, ["أنا طالب", ""], 0)
    assert c["writing_score"] == 50


def test_passage_answers_per_passage():
    passages = [{"id": "p1", "questions": [_mcq(), _mcq()]}, {"id": "p2", "questions": [_mcq()]}]
    c = ex.grade_answers(_exam(passages=passages), [], [], [["a", "b"], ["a"]], [], 0)
    assert c["passage_correct"] == 2
    c = ex.grade_answers(_exam(passages=passages), [], [], [["a"]], [], 0)
    assert c["passage_correct"] == 1, "yetishmagan matn javoblari — xato"


def test_no_sections_default_to_full_score():
    c = ex.grade_answers(_exam(n_w=0, n_s=0), [], [], None, None, 0)
    assert c["writing_score"] == 100 and c["speaking_score"] == 100


# ── Diktant tekshiruvi webapp/src/pages/v2/answerCheck.ts bilan bir xil ──


@pytest.mark.skipif(not shutil.which("node") or not ESBUILD.exists(), reason="node yoki webapp/node_modules yo'q")
def test_dictation_check_matches_typescript():
    rnd = random.Random(3)
    cases = []
    for level in LEVELS:
        for it in ex.load_pool(level)["listening"]:
            if it["type"] != "dictation":
                continue
            ans = it["answer"]
            bare = ex.norm_ar(ans)
            letters = [c for c in bare if c != " "]
            wrong = bare[:-1] + ("ب" if bare[-1] != "ب" else "ت")
            swapped = bare.replace("ا", "ى") if "ا" in bare else bare + "ى"
            typed = {
                ans, bare, ans.replace("َ", ""), wrong, swapped, bare[::-1], bare + "ن", "", "   ",
                bare.replace("ء", "ئ"), bare.replace("ة", "ه"), bare.replace("ى", "ي"),
                "".join(rnd.sample(letters, len(letters))), "أ" + bare, bare + ".", bare + " ",
            }
            cases += [(ans, t) for t in typed]
    # shadda va ى/ي — accept bilan ham
    cases += [("تَعَلُّم", "تعللم"), ("تَعَلُّم", "تعلم"), ("مَتى", "متي"), ("مَدِينَة", "مدينه")]
    assert len(cases) > 50
    payload = [["arOk", a, t, {"accept": [], "mode": "strict"}] for a, t in cases]
    r = subprocess.run(["node", str(RUNNER)], input=json.dumps(payload), capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    ts = [x["ok"] for x in json.loads(r.stdout)]
    py = [ex.ar_dictation_ok(a, t) for a, t in cases]
    diff = [(c, p, t) for c, p, t in zip(cases, py, ts) if p != t]
    assert not diff, diff[:5]


# ── API ──


@pytest.fixture
async def api(session, make_user, monkeypatch):
    from api import exam as exam_api
    from db.session import get_session
    from main import app
    from services.telegram_auth import get_current_user

    user = await make_user("Imtihonchi")
    # A1 darajasidagi o'quvchi A0 imtihonini topshira oladi (past daraja doim ochiq)
    session.add(Plan(user_id=user.id, level="A1", target_level="B1", target_date="2027-01-01"))
    await session.commit()

    async def fake_cert(sess, user_id, holder, level, total, parts):
        return SimpleNamespace(cert_id=f"ARB-{level}-TEST", png_path="x.png", pdf_path=None)

    monkeypatch.setattr(exam_api, "issue_certificate", fake_cert)

    async def _session():
        yield session

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: user
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    try:
        yield client, user
    finally:
        await client.aclose()
        app.dependency_overrides.clear()


async def _start(client, level="A0"):
    r = await client.post(f"/api/exam/start?v=2&level={level}", content="{}")
    assert r.status_code == 200, r.text
    return r.json()


async def _attempt(session, attempt_id) -> ExamAttempt:
    return (await session.execute(select(ExamAttempt).where(ExamAttempt.id == attempt_id))).scalar_one()


def _correct_answers(full: dict) -> dict:
    """To'liq (bazadagi) imtihondan to'g'ri javoblar — variantli savollarga javob matni, diktantga yozuv."""
    return {
        "reading": [i["answer"] for i in full["reading"]],
        "listening": [i["answer"] for i in full["listening"]],
        "passages": [[q["answer"] for q in p["questions"]] for p in full.get("passages") or []],
        "writing": ["أنا طالب"] * len(full["writing"]),
        "speaking_done": len(full["speaking"]),
    }


async def test_start_requires_new_client(api):
    client, _ = api
    r = await client.post("/api/exam/start?level=A0", content="{}")
    assert r.status_code == 426
    assert "yangilangan" in r.json()["detail"]


async def test_start_response_has_no_answers(api, session):
    client, _ = api
    data = await _start(client)
    assert not SECRET_KEYS & set(_keys(data))
    assert data["attempt_id"] and data["reading"] and data["listening"]
    stored = json.loads((await _attempt(session, data["attempt_id"])).questions_json)
    assert any("answer" in i for i in stored["reading"]), "to'liq nusxa bazada qoladi"


async def test_correct_answers_pass_and_issue_certificate(api, session):
    client, user = api
    data = await _start(client)
    full = json.loads((await _attempt(session, data["attempt_id"])).questions_json)
    body = {"attempt_id": data["attempt_id"], **_correct_answers(full), "holder_name": "Ali Valiyev"}
    r = await client.post("/api/exam/submit", json=body)
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["total"] == 100 and res["passed"] is True
    assert res["certificate"]["cert_id"].startswith("ARB-A0")
    xp = (await session.execute(select(XpLog).where(XpLog.user_id == user.id))).scalars().all()
    assert [x.amount for x in xp] == [50]


async def test_forged_scores_are_ignored(api, session):
    """Eski usul: ball raqamlari 100 — ammo javoblar yo'q. Natija: yiqildi, sertifikat yo'q."""
    client, user = api
    data = await _start(client)
    body = {
        "attempt_id": data["attempt_id"],
        "reading": [""] * len(data["reading"]),
        "listening": [""] * len(data["listening"]),
        "writing": [],
        "speaking_done": 0,
        "reading_correct": 999,
        "listening_correct": 999,
        "writing_score": 100,
        "speaking_score": 100,
    }
    r = await client.post("/api/exam/submit", json=body)
    assert r.status_code == 200
    res = r.json()
    assert res["reading"] == 0 and res["listening"] == 0
    assert res["passed"] is False and res["certificate"] is None
    assert (await session.execute(select(XpLog).where(XpLog.user_id == user.id))).first() is None


async def test_wrong_answers_fail(api, session):
    client, _ = api
    data = await _start(client)
    full = json.loads((await _attempt(session, data["attempt_id"])).questions_json)

    def wrong(it):
        return next((o for o in it.get("options") or [] if o != it["answer"]), "ء")

    body = {
        "attempt_id": data["attempt_id"],
        "reading": [wrong(i) for i in full["reading"]],
        "listening": [wrong(i) for i in full["listening"]],
        "passages": [],
        "writing": [],
        "speaking_done": 0,
    }
    res = (await client.post("/api/exam/submit", json=body)).json()
    assert res["reading"] == 0 and res["listening"] == 0
    assert res["passed"] is False


async def test_legacy_submit_is_rejected_without_burning_the_attempt(api, session):
    """Eski mijoz faqat raqam yuboradi — 426, urinish yakunlanmaydi (24 soat qulf yo'q)."""
    client, _ = api
    data = await _start(client)
    r = await client.post(
        "/api/exam/submit",
        json={
            "attempt_id": data["attempt_id"],
            "reading_correct": 8,
            "listening_correct": 8,
            "writing_score": 100,
            "speaking_score": 100,
        },
    )
    assert r.status_code == 426
    att = await _attempt(session, data["attempt_id"])
    assert att.finished_at is None
    # o'quvchi qayta boshlay oladi
    assert (await client.post("/api/exam/start?v=2&level=A0", content="{}")).status_code == 200


async def test_attempt_cannot_be_submitted_twice(api, session):
    client, _ = api
    data = await _start(client)
    body = {"attempt_id": data["attempt_id"], "reading": [], "listening": [], "writing": [], "speaking_done": 0}
    assert (await client.post("/api/exam/submit", json=body)).status_code == 200
    assert (await client.post("/api/exam/submit", json=body)).status_code == 409


async def test_rejected_dictation_goes_to_answer_log(api, session, monkeypatch):
    client, user = api
    real_build = ex.build_exam

    def with_dictation(level, seen=None):
        # A0 tinglashida diktant ~96% tushadi — testni tasodifga bog'lamaymiz
        for _ in range(200):
            exam = real_build(level, seen)
            if any(q["type"] == "dictation" for q in exam["listening"]):
                return exam
        raise AssertionError("diktantli imtihon yig'ilmadi")

    monkeypatch.setattr(ex, "build_exam", with_dictation)
    data = await _start(client, "A0")
    full = json.loads((await _attempt(session, data["attempt_id"])).questions_json)
    listening = [i["answer"] for i in full["listening"]]
    idx = next(i for i, q in enumerate(full["listening"]) if q["type"] == "dictation")
    listening[idx] = "ظظظ"
    body = {
        "attempt_id": data["attempt_id"],
        "reading": [i["answer"] for i in full["reading"]],
        "listening": listening,
        "writing": [],
        "speaking_done": 0,
    }
    assert (await client.post("/api/exam/submit", json=body)).status_code == 200
    rows = (await session.execute(select(AnswerLog).where(AnswerLog.user_id == user.id))).scalars().all()
    assert [(r.context, r.ex_type, r.given) for r in rows] == [("exam:listening", "dictation", "ظظظ")]


async def test_oversized_payload_rejected(api):
    client, _ = api
    data = await _start(client)
    body = {"attempt_id": data["attempt_id"], "reading": ["x" * 500], "listening": [], "writing": [], "speaking_done": 0}
    assert (await client.post("/api/exam/submit", json=body)).status_code == 422
