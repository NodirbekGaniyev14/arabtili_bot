"""K28 — dars ko'nikma fazalari: 🗣 GAPIRISH eshitadi (STT + solishtirish), ✍️ YOZISH o'qiydi (matn/surat → AI).

Egasi (2026-09-28): «gapirish qismida bot hech narsani eshitmaydi, yozish qismida yozganimni o'qimaydi».
GAPIRISH fazasida mikrofon umuman yo'q edi; YOZISH AI xatosini jimgina «o'chiq» deb qaytarardi.
"""

import io
import json
from pathlib import Path

import httpx
import pytest

from db.models import Plan
from services import lesson_skills as ls

ROOT = Path(__file__).resolve().parent.parent


# ── Gapirish: solishtirish ──


@pytest.mark.parametrize(
    "target,heard,score",
    [
        ("ب", "باء", 100),
        ("ب", "با با با", 100),  # uch marta takrorladi
        ("ب", "بو", 100),  # o'zbekcha «bo»
        ("ط", "طاء", 100),
        ("ا", "ألف", 100),
        ("و", "واو", 100),
        ("ء", "همزة", 100),
        ("ط", "كتاب", 0),  # boshqa so'z
        ("بَ", "با", 100),
        ("بِ", "بي", 100),
        ("بُ", "بو", 100),
        ("بت", "باء تاء", 100),
        ("مَنْ", "من", 100),
        ("البَيْتُ كَبِيرٌ", "البيت كبير", 100),
    ],
)
def test_speak_score_accepts(target, heard, score):
    assert ls.speak_score(target, heard)["score"] == score


def test_speak_score_explains_mistakes():
    r = ls.speak_score("ط", "تاء")  # qalin ط o'rniga ingichka ت
    assert r["score"] == 60 and r["words"][0]["close"] and "qalin" in r["tip_uz"]
    r = ls.speak_score("بِ", "با")  # kasra o'rniga fatha
    assert r["score"] == 50 and "kasra" in r["tip_uz"]
    r = ls.speak_score("بت", "باء")  # ikkinchi harf aytilmadi
    assert r["score"] == 50 and [w["ok"] for w in r["words"]] == [True, False]
    r = ls.speak_score("البَيْتُ كَبِيرٌ", "البيت صغير")
    assert 0 < r["score"] < 80 and [w["ok"] for w in r["words"]] == [True, False]
    r = ls.speak_score("البَيْتُ كَبِيرٌ", "")
    assert r["score"] == 0 and "tushunilmadi" in r["tip_uz"]


def test_modes_and_tts_text():
    assert ls.mode("ب") == "letter" and ls.tts_text("ب") == "بَاء", "harf — nomi aytiladi"
    assert ls.mode("بَ") == "syllable" and ls.tts_text("بَ") == "بَ، بَ"
    assert ls.mode("بت") == "letters" and ls.tts_text("بت") == "بَاء، تَاء"
    assert ls.mode("كتب") == "text" and ls.mode("مَنْ") == "text" and ls.mode("قَالَ يَقُولُ") == "text"


def test_every_lesson_target_is_scorable():
    """Har darsdagi har gapirish namunasi: rejim aniqlanadi, TTS matni bor, o'zi bilan 100 ball."""
    n = 0
    for f in sorted((ROOT / "content" / "modules").rglob("*.json")):
        lesson = json.loads(f.read_text(encoding="utf-8"))
        for t in ls.speak_targets(lesson):
            n += 1
            assert ls.tts_text(t).strip(), (f.stem, t)
            spoken = ls.tts_text(t).replace("،", " ")
            assert ls.speak_score(t, spoken)["score"] >= 80, (f.stem, t, spoken)
    assert n > 600


def test_lesson_content_for_ai():
    lesson = json.loads((ROOT / "content" / "modules" / "a1" / "a1-01.json").read_text(encoding="utf-8"))
    c = ls.lesson_content(lesson)
    assert "Words:" in c and "Examples:" in c
    sys = ls.writing_system(lesson, "Sifat", "A1", photo=True)[0]["text"]
    assert lesson["skills"]["writing"]["task_uz"] in sys and "rotated" in sys


# ── API ──


def _png(w=600, h=400) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (w, h), "white").save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
def client(session, monkeypatch):
    from api import v2
    from db.session import get_session
    from main import app
    from services.telegram_auth import get_current_user

    v2._lesson_ai_used.clear()
    v2._stt_used.clear()

    async def _session():
        yield session

    state = {"user": None}
    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    c = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    try:
        yield c, state
    finally:
        app.dependency_overrides.clear()


async def _user(session, make_user, level="A1"):
    u = await make_user("Sinov")
    session.add(Plan(user_id=u.id, level=level, target_level="A2", target_date="2027-01-01"))
    await session.flush()
    return u


@pytest.mark.asyncio
async def test_speak_api(client, session, make_user, monkeypatch):
    from config import settings
    from services import stt

    c, state = client
    state["user"] = await _user(session, make_user)
    monkeypatch.setattr(settings, "stt_api_key", "k")
    heard = {"text": "البيت كبير"}

    async def fake_transcribe(data, filename="", mime="", prompt="", lang="ar"):
        assert prompt == "", "maqsad matn Whisper'ga berilmaydi"
        return heard["text"]

    monkeypatch.setattr(stt, "transcribe", fake_transcribe)
    lesson = (await c.get("/api/v2/lessons/a1-01")).json()
    assert lesson["voice"] is True
    files = {"file": ("speech.webm", b"x" * 3000, "audio/webm")}
    r = await c.post("/api/v2/lessons/a1-01/speak", data={"idx": "0"}, files=files)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["score"] == 100 and d["transcript"] == "البيت كبير" and d["mode"] == "text"

    heard["text"] = "الولد طويل"
    d = (await c.post("/api/v2/lessons/a1-01/speak", data={"idx": "0"}, files=files)).json()
    assert d["score"] < 50 and not any(w["ok"] for w in d["words"])

    assert (await c.post("/api/v2/lessons/a1-01/speak", data={"idx": "9"}, files=files)).status_code == 404
    assert (await c.post("/api/v2/lessons/zz-99/speak", data={"idx": "0"}, files=files)).status_code == 404
    assert (await c.post("/api/v2/lessons/a1-01/speak", data={"idx": "0"}, files={"file": ("s.webm", b"", "audio/webm")})).status_code == 422

    monkeypatch.setattr(settings, "stt_api_key", "")
    assert (await c.post("/api/v2/lessons/a1-01/speak", data={"idx": "0"}, files=files)).status_code == 503


@pytest.mark.asyncio
async def test_speak_audio_endpoint(client, monkeypatch, tmp_path):
    from services import tts

    c, _ = client
    said = {}

    async def fake_synth(text, level):
        said["text"], said["level"] = text, level
        return "a" * 24

    monkeypatch.setattr(tts, "synthesize", fake_synth)
    monkeypatch.setattr(tts, "path_for", lambda key: tmp_path / "x.mp3")
    (tmp_path / "x.mp3").write_bytes(b"ID3" + b"\x00" * 50)
    r = await c.get("/api/v2/lessons/a0-10/speak/0.mp3")  # initData'siz — <audio src>
    assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg"
    assert said == {"text": "طَاء", "level": "A0"}, "harf — nomi bilan aytiladi"
    assert (await c.get("/api/v2/lessons/a0-10/speak/7.mp3")).status_code == 404


def _reply(**kw) -> ls.LessonWritingReply:
    base = dict(is_handwriting=True, read_ar="البَابُ كَبِيرٌ", ok=False, score=70, corrected_ar="البَابُ كَبِيرٌ",
                feedback_uz="Yaxshi.", tips_uz=["a", "b", "c"])
    base.update(kw)
    return ls.LessonWritingReply(**base)


@pytest.mark.asyncio
async def test_writing_text_api(client, session, make_user, monkeypatch):
    from config import settings
    from services import alerts, tutor

    c, state = client
    state["user"] = await _user(session, make_user)
    monkeypatch.setattr(settings, "anthropic_api_key", "k")
    seen = {}

    async def fake_call(system, msgs, schema, model=None, max_tokens=400):
        seen.update(system=system[0]["text"], content=msgs[0]["content"], model=model, schema=schema)
        return _reply(ok=True), {"in": 800, "out": 90}

    monkeypatch.setattr(tutor, "_call", fake_call)
    r = await c.post("/api/v2/eval/writing", json={"lesson_id": "a1-01", "text": "البَابُ كَبِيرٌ"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ai"] and d["ok"] and d["corrected_ar"] == "" and len(d["tips_uz"]) == 2
    assert "Eshik katta" in seen["system"] and "البَابُ كَبِيرٌ" in seen["content"]
    assert seen["model"] == settings.tutor_model and seen["schema"] is ls.LessonWritingReply, "matn — arzon model"

    assert (await c.post("/api/v2/eval/writing", json={"lesson_id": "a1-01", "text": "  "})).status_code == 422
    assert (await c.post("/api/v2/eval/writing", json={"lesson_id": "zz", "text": "x"})).status_code == 404

    # AI xatosi jim yutilmaydi: kalit rad etildi → adminga ogohlantirish, o'quvchiga sabab
    fired = []
    monkeypatch.setattr(alerts, "fire", lambda bot, kind, detail="": fired.append(kind))

    async def failing(*a, **k):
        raise tutor.TutorUnavailable(tutor._BUSY, "auth")

    monkeypatch.setattr(tutor, "_call", failing)
    d = (await c.post("/api/v2/eval/writing", json={"lesson_id": "a1-01", "text": "x"})).json()
    assert d["ai"] is False and d["error"] == "auth" and fired == ["auth"]


@pytest.mark.asyncio
async def test_writing_photo_api(client, session, make_user, monkeypatch):
    from api import v2
    from config import settings
    from services import tutor

    c, state = client
    state["user"] = await _user(session, make_user, level="A0")
    monkeypatch.setattr(settings, "anthropic_api_key", "k")
    seen = {}

    async def fake_call(system, msgs, schema, model=None, max_tokens=400):
        seen.update(model=model, kinds=[b["type"] for b in msgs[0]["content"]], system=system[0]["text"])
        return _reply(read_ar="ن ن ن\nي ي ي", ok=True), {"in": 1500, "out": 90}

    monkeypatch.setattr(tutor, "_call", fake_call)
    r = await c.post("/api/v2/eval/writing-photo", data={"lesson_id": "a0-04"}, files={"file": ("p.png", _png(), "image/png")})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ai"] and d["read_ar"] == "ن ن ن\nي ي ي" and d["is_handwriting"] is True
    assert seen["kinds"] == ["image", "text"] and seen["model"] == settings.writing_model, "surat — vision modeli"
    assert "Daftaringizga" in seen["system"]

    # Surat emas / bo'sh / katta
    bad = await c.post("/api/v2/eval/writing-photo", data={"lesson_id": "a0-04"}, files={"file": ("x.txt", b"abc", "text/plain")})
    assert bad.status_code == 422
    bad = await c.post("/api/v2/eval/writing-photo", data={"lesson_id": "a0-04"}, files={"file": ("x.png", b"\x00" * 10, "image/png")})
    assert bad.status_code == 422

    # Yozuv ko'rinmadi → ball 0
    async def blank(*a, **k):
        return _reply(is_handwriting=False, read_ar="", score=40, ok=True), {}

    monkeypatch.setattr(tutor, "_call", blank)
    d = (await c.post("/api/v2/eval/writing-photo", data={"lesson_id": "a0-04"}, files={"file": ("p.png", _png(), "image/png")})).json()
    assert d["is_handwriting"] is False and d["score"] == 0 and d["ok"] is False

    # Kunlik limit (token xarajati himoyasi)
    v2._lesson_ai_used[state["user"].id] = (v2.datetime.now(v2.timezone.utc).strftime("%Y-%m-%d"), v2.LESSON_AI_DAILY_CAP)
    r = await c.post("/api/v2/eval/writing", json={"lesson_id": "a1-01", "text": "x"})
    assert r.status_code == 429


@pytest.mark.asyncio
async def test_handwriting_uses_vision_model_with_fallback(monkeypatch):
    """Yozuv mashqi: WRITING_MODEL xato bersa (nomi/ruxsat) — asosiy model bilan qayta uriniladi."""
    from config import settings
    from services import tutor, writing

    monkeypatch.setattr(settings, "anthropic_api_key", "k")
    monkeypatch.setattr(settings, "writing_model", "claude-sonnet-5-5")
    calls = []

    class FakeMessages:
        async def parse(self, model, **kw):
            calls.append(model)
            if model == "claude-sonnet-5-5":
                raise RuntimeError("not_found_error: model")
            raise RuntimeError("structured off")

        async def create(self, model, **kw):
            calls.append(model + ":json")
            if model == "claude-sonnet-5-5":
                raise RuntimeError("not_found_error: model")

            class R:
                content = [type("B", (), {"type": "text", "text": json.dumps({
                    "is_handwriting": True, "read_ar": "بيت", "accuracy": 90, "neatness": 4, "missing_words": [],
                    "wrong_words": [], "tips_uz": ["x"], "praise_uz": "Zo'r"})})()]
                usage = None

            return R()

    class FakeClient:
        def __init__(self, **kw):
            self.messages = FakeMessages()

    import anthropic

    monkeypatch.setattr(anthropic, "AsyncAnthropic", FakeClient)
    out, usage = await writing.check("A1", writing.text_for("A1"), writing.prepare_image(_png())[0], "image/jpeg")
    assert out.read_ar == "بيت" and out.accuracy == 90
    assert calls[:2] == ["claude-sonnet-5-5", "claude-sonnet-5-5:json"] and calls[-1] == settings.tutor_model + ":json"
    assert usage["model"] == settings.tutor_model


# ── K28: Sonnet 5/5.5 — fikrlash tokenlari max_tokens ga kiradi ──


def test_output_budget_only_for_thinking_models():
    from services import tutor

    assert tutor.output_budget("claude-haiku-4-5-20251001", 400) == 400, "Haiku o'zgarmaydi"
    assert tutor.output_budget("claude-sonnet-4-6", 400) == 400, "Sonnet 4.6 — fikrlash o'zi yoqilmaydi"
    for m in ("claude-sonnet-5", "claude-sonnet-5-5", "claude-opus-5-5", "claude-fable-5-1"):
        assert tutor.output_budget(m, 400) == tutor.THINKING_HEADROOM, m
        assert tutor.output_budget(m, 9000) == 9000, "kattasini kamaytirmaydi"


@pytest.mark.asyncio
async def test_call_passes_headroom_to_thinking_models(monkeypatch):
    """400 tokenlik cheklov bilan Sonnet JSON'ni kesardi → ikki bekor chaqiruv + jim Haiku. Endi zaxira bor."""
    import anthropic

    from config import settings
    from services import tutor

    monkeypatch.setattr(settings, "anthropic_api_key", "k")
    seen = []

    class FakeMessages:
        async def parse(self, model, max_tokens, **kw):
            seen.append((model, max_tokens))
            return type("R", (), {"parsed_output": _reply(ok=True), "usage": None})()

    class FakeClient:
        def __init__(self, **kw):
            self.messages = FakeMessages()

    monkeypatch.setattr(anthropic, "AsyncAnthropic", FakeClient)
    for model in ("claude-haiku-4-5-20251001", "claude-sonnet-5-5"):
        out, usage = await tutor._call([{"type": "text", "text": "s"}], [{"role": "user", "content": "x"}],
                                       ls.LessonWritingReply, model, max_tokens=400)
        assert usage["model"] == model and out.ok
    assert seen == [("claude-haiku-4-5-20251001", 400), ("claude-sonnet-5-5", tutor.THINKING_HEADROOM)]


def test_new_ai_feature_is_named_in_usage_report():
    from services import ai_usage

    assert "lesson_writing" in ai_usage.FEATURES
    assert ai_usage.short_model("claude-sonnet-5-5") == "Sonnet 5.5"
    assert ai_usage.prices_for("claude-sonnet-5-5") == {"in": 2.0, "out": 10.0, "cache_read": 0.2, "cache_write": 2.5}


def test_f180_letter_lessons_review_previous_letters():
    """#F180 (o'quvchi taklifi: «ko'proq gapirish, harflarni talaffuz qilish»): harf darsida GAPIRISH 2–3 harf bilan
    tugamaydi — oldingi darslar harflari ham takrorlanadi; harakat/so'z darslariga qo'shilmaydi."""
    from services.curriculum import load_lesson_v2
    from services.lesson_skills import MAX_SPEAK_TARGETS, letter_review, speak_targets

    a01 = load_lesson_v2("a0-01")
    assert letter_review(a01) == [] and speak_targets(a01) == ["ا", "ب", "م", "ل", "و"], "birinchi dars — takror yo'q"
    a09 = load_lesson_v2("a0-09")
    assert speak_targets(a09)[:2] == ["ص", "ض"] and {"س", "ش"} <= set(letter_review(a09)), "yaqin juftlik (س ش) takrorda"
    for lid in ("a0-02", "a0-03", "a0-10", "a0-16"):
        t = speak_targets(load_lesson_v2(lid))
        assert 5 <= len(t) <= MAX_SPEAK_TARGETS and len(set(t)) == len(t), (lid, t)
    assert letter_review(load_lesson_v2("a0-21")) == [], "bo'g'in (بَ) darsiga qo'shilmaydi"
    assert letter_review(load_lesson_v2("a1-01")) == []
