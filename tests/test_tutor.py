"""AI ustoz (K17): prompt tuzilishi, tarix, talaffuz bali, API oqimi (mock)."""

import json

import httpx
import pytest

from services import tutor


# ── Mavzular va lug'at ──


def test_topics_recommended_first():
    lst = tutor.topic_list("A1")
    ids = [t["id"] for t in lst]
    assert set(ids) == set(tutor.TOPIC_BY_ID)
    # A1 uchun mos mavzular oldinda, B1+ (ish, munozara) oxirida
    rec = [t["recommended"] for t in lst]
    assert rec == sorted(rec, reverse=True)
    assert not next(t for t in lst if t["id"] == "munozara")["recommended"]
    assert next(t for t in lst if t["id"] == "tanishish")["recommended"]


def test_topic_words_respect_level():
    from services.vocab import load_level

    words = tutor.topic_words("A0", ["ovqat"], set())
    a0 = {w["ar"] for w in load_level("A0")}
    assert words and all(w["ar"] in a0 for w in words)
    # A1'da tema so'zlari oldinda, keyin umumiy chastota bilan to'ladi
    words = tutor.topic_words("A1", ["restoran", "ovqat"], set())
    assert len(words) == tutor.TOPIC_WORDS_LIMIT
    assert len({w["ar"] for w in words}) == len(words), "takror so'z"


def test_topic_words_exclude_known():
    words = tutor.topic_words("A1", [], set())
    first = words[0]["ar"]
    from services.reference import normalize

    again = tutor.topic_words("A1", [], {normalize(first)})
    assert first not in {w["ar"] for w in again}


# ── Prompt ──


def test_system_blocks_and_cache():
    sysb = tutor.build_system(
        name="Nodir",
        level="A2",
        topic=tutor.TOPIC_BY_ID["bozor"],
        known=[{"ar": "كِتَاب", "translit": "kitaab", "uz": "kitob"}],
        extra=tutor.topic_words("A2", ["xarid"], set()),
    )
    assert len(sysb) == 2
    assert "cache_control" not in sysb[0]
    assert sysb[1]["cache_control"] == {"type": "ephemeral"}
    text = sysb[1]["text"]
    assert "Level: A2" in text and "Nodir" in text
    assert tutor.LEVEL_PROFILES["A2"] in text
    assert "كِتَاب | kitaab | kitob" in text


def test_unknown_level_falls_back_to_a0():
    sysb = tutor.build_system(
        name="", level="ZZ", topic=tutor.TOPIC_BY_ID["erkin"], known=[], extra=[]
    )
    assert "Level: A0" in sysb[1]["text"]


def test_trim_history_prepends_start_and_merges():
    h = [
        {"role": "assistant", "content": "ochilish"},
        {"role": "user", "content": "a"},
        {"role": "user", "content": "b"},
        {"role": "assistant", "content": "c"},
        {"role": "user", "content": "d"},
    ]
    out = tutor._trim_history(h)
    assert out[0] == {"role": "user", "content": "[START]"}
    assert out[1]["role"] == "assistant"
    assert out[2] == {"role": "user", "content": "a\nb"}
    assert out[-1]["role"] == "user"


def test_trim_history_window():
    h = [{"role": "user" if i % 2 else "assistant", "content": str(i)} for i in range(30)]
    out = tutor._trim_history(h)
    assert len(out) <= tutor.HISTORY_TURNS + 1
    assert out[0]["role"] == "user"


# ── Talaffuz ──


def test_pronunciation_perfect_ignores_harakat_and_punct():
    r = tutor.pronunciation_score("أَهْلًا وَسَهْلًا، كَيْفَ حَالُكَ؟", "اهلا وسهلا كيف حالك")
    assert r["score"] == 100
    assert all(w["ok"] for w in r["words"]) and len(r["words"]) == 4


def test_pronunciation_partial_marks_missing_words():
    r = tutor.pronunciation_score("أَهْلًا وَسَهْلًا كَيْفَ حَالُكَ", "اهلا كيف")
    assert 30 < r["score"] < 80
    assert [w["ok"] for w in r["words"]] == [True, False, True, False]


def test_pronunciation_empty():
    assert tutor.pronunciation_score("أَهْلًا", "")["score"] == 0
    assert tutor.pronunciation_score("", "x") == {"score": 0, "words": []}


def _marks(r):
    return ["ok" if w["ok"] else "~" if w["close"] else "x" for w in r["words"]]


def test_pronunciation_close_words_whisper_spelling():
    """TTS→Whisper aylanma sinovi (2026-09-17): Whisper qisqa unlini harf qilib yozadi,
    ta-marbuta/alif-maqsura almashadi — bu talaffuz xatosi emas, «yaqin» (sariq)."""
    r = tutor.pronunciation_score("مَا عَمَلُكَ؟", "ما عملوك؟")
    assert _marks(r) == ["ok", "~"] and 85 <= r["score"] < 100
    assert _marks(tutor.pronunciation_score("اِحْكِ عَنْ شَخْصٍ", "احكي عن شخص")) == ["~", "ok", "ok"]
    assert _marks(tutor.pronunciation_score("مَا أَكْبَرُ تَحَدٍّ", "ما أكبر تحدي")) == ["ok", "ok", "~"]
    assert _marks(tutor.pronunciation_score("اللَّوْزُ فِي الحَلْوَى.", "اللوز في الحلوة")) == ["ok", "ok", "~"]
    assert _marks(tutor.pronunciation_score("العَقَارِيَّ", "العقارية")) == ["~"]
    # Qo'shma so'zni Whisper bo'lib yozdi — to'liq ok
    r = tutor.pronunciation_score("المَسَافَةُ عِشْرُونَ كِيلُومِتْرًا.", "المسافة عشرون كيلو متراً.")
    assert _marks(r) == ["ok", "ok", "ok"] and r["score"] == 100
    # Hamza tashuvchisi farqi — bir xil so'z
    assert tutor.pronunciation_score("مَسْؤُول", "مسئول")["score"] == 100
    # Haqiqiy xatolar qizil qoladi: qisqa so'z aniq mos kelishi shart, undosh almashuvi jarima
    assert _marks(tutor.pronunciation_score("كَمْ عُمْرُكَ؟", "كان عمرك؟")) == ["x", "ok"]
    r = tutor.pronunciation_score("قَلْبٌ", "كلب")
    assert _marks(r) == ["x"] and r["score"] < 50
    # Bitta undosh almashuvi (ش→س) — Whisper toza TTS audioda ham shunday yozadi: sariq
    assert _marks(tutor.pronunciation_score("الجُنْدِيُّ شُجَاعٌ.", "الجندي سجاع.")) == ["ok", "~"]


# ── reply(): Anthropic mock ──


def _reply_json(**over):
    base = {
        "ar": "أَهْلًا! مَا اسْمُكَ؟",
        "translit": "ahlan! maa ismuka?",
        "uz": "Salom! Isming nima?",
        "correction_ok": True,
        "fixed_ar": "",
        "note_uz": "",
        "hint_uz": "Ismingizni ayting",
        "new_words": [{"ar": "اِسْم", "translit": "ism", "uz": "ism"}] * 3,
        "done": True,
    }
    base.update(over)
    return json.dumps(base, ensure_ascii=False)


def _message(text, usage=None):
    return {
        "id": "m",
        "type": "message",
        "role": "assistant",
        "model": "x",
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": usage or {"input_tokens": 10, "output_tokens": 5},
    }


@pytest.fixture
def anthropic_mock(monkeypatch):
    """AsyncAnthropic'ni MockTransport bilan o'raydi; handler ro'yxati navbatma-navbat."""
    import anthropic

    from config import settings

    monkeypatch.setattr(settings, "anthropic_api_key", "test")
    calls: list[dict] = []
    handlers: list = []

    def transport(request: httpx.Request):
        body = json.loads(request.content)
        calls.append(body)
        h = handlers.pop(0)
        return h(body) if callable(h) else h

    orig = anthropic.AsyncAnthropic

    class Patched(orig):
        def __init__(self, **kw):
            super().__init__(
                http_client=httpx.AsyncClient(transport=httpx.MockTransport(transport)), **kw
            )

    monkeypatch.setattr(anthropic, "AsyncAnthropic", Patched)
    return calls, handlers


@pytest.mark.asyncio
async def test_reply_structured(anthropic_mock):
    calls, handlers = anthropic_mock
    handlers.append(
        httpx.Response(
            200,
            json=_message(
                _reply_json(),
                {"input_tokens": 100, "output_tokens": 50, "cache_read_input_tokens": 4200},
            ),
        )
    )
    out, usage = await tutor.reply(
        name="N", level="A1", topic_id="tanishish", history=[], known=[]
    )
    assert out.ar.startswith("أَهْلًا")
    assert len(out.new_words) == 2, "ko'pi bilan 2 yangi so'z"
    assert out.done is False, "6 javobdan oldin yakunlanmaydi"
    assert usage["cache_read"] == 4200
    body = calls[0]
    assert body["messages"] == [{"role": "user", "content": "[START]"}]
    assert body["max_tokens"] == tutor.MAX_TOKENS
    assert "output_config" in body, "structured output so'raladi"
    assert body["system"][-1]["cache_control"] == {"type": "ephemeral"}


@pytest.mark.asyncio
async def test_reply_json_fallback_when_structured_rejected(anthropic_mock):
    calls, handlers = anthropic_mock
    handlers.append(
        httpx.Response(
            400, json={"type": "error", "error": {"type": "invalid_request_error", "message": "no"}}
        )
    )
    handlers.append(
        httpx.Response(
            200, json=_message("```json\n" + _reply_json(correction_ok=False, fixed_ar="أَنَا") + "\n```")
        )
    )
    hist = [{"role": "assistant", "content": "x"}, {"role": "user", "content": "men"}]
    out, _ = await tutor.reply(name="N", level="A0", topic_id="oila", history=hist, known=[])
    assert len(calls) == 2 and "output_config" not in calls[1]
    assert out.correction_ok is False and out.fixed_ar == "أَنَا"


@pytest.mark.asyncio
async def test_reply_unavailable_on_credit_error(anthropic_mock):
    _, handlers = anthropic_mock
    err = httpx.Response(
        400,
        json={
            "type": "error",
            "error": {
                "type": "invalid_request_error",
                "message": "Your credit balance is too low to access the Anthropic API.",
            },
        },
    )
    handlers.extend([err, err])
    with pytest.raises(tutor.TutorUnavailable) as ei:
        await tutor.reply(name="N", level="A0", topic_id="oila", history=[], known=[])
    assert "band" in ei.value.message_uz


@pytest.mark.asyncio
async def test_reply_without_key(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "anthropic_api_key", "")
    with pytest.raises(tutor.TutorUnavailable):
        await tutor.reply(name="N", level="A0", topic_id="oila", history=[], known=[])


@pytest.mark.asyncio
async def test_known_words_skip_letters(session, make_user):
    from db.models import UserWord

    u = await make_user()
    session.add_all(
        [
            UserWord(user_id=u.id, ar="ب", uz="be", kind="letter", due_date="2026-01-01"),
            UserWord(user_id=u.id, ar="كِتَاب", uz="kitob", kind="word", reps=3, due_date="2026-01-01"),
            UserWord(user_id=u.id, ar="قَلَم", uz="qalam", kind="word", reps=1, due_date="2026-01-01"),
        ]
    )
    await session.flush()
    words = await tutor.known_words(session, u.id)
    assert [w["ar"] for w in words] == ["كِتَاب", "قَلَم"]


# ── TTS kalit/cache ──


def test_tts_key_depends_on_level_rate(tmp_path, monkeypatch):
    from services import tts

    monkeypatch.setattr(tts, "cache_dir", lambda: tmp_path)
    k1 = tts.key_for("سَلَام", "A0")
    k2 = tts.key_for("سَلَام", "B2")
    assert k1 != k2 and len(k1) == 24
    assert tts.path_for(k1) == tmp_path / f"{k1}.mp3"
    assert tts.schedule("", "A0") == ""


# ── Mock imtihon ──


def test_mock_list_recommended_first():
    lst = tutor.mock_list("A1")
    assert {m["id"] for m in lst} == set(tutor.MOCK_BY_ID)
    rec = [m["recommended"] for m in lst]
    assert rec == sorted(rec, reverse=True)
    assert all(m["questions"] == tutor.MOCK_QUESTIONS for m in lst)


def test_mock_system_prompt():
    sysb = tutor.build_system(
        name="N", level="A2", topic=tutor.TOPIC_BY_ID["erkin"], known=[], extra=[],
        mock=tutor.MOCK_BY_ID["shifokor"],
    )
    assert "SPEAKING MOCK EXAM" in sysb[0]["text"]
    assert f"Exactly {tutor.MOCK_QUESTIONS} questions" in sysb[0]["text"]
    assert "Exam field: Shifokor" in sysb[1]["text"]


def _mock_json(score=70, done=False, vocab=None, grammar=None, content=None):
    return json.dumps(
        {"ar": "سُؤَال", "translit": "su'aal", "uz": "savol", "score": score,
         "vocab": score if vocab is None else vocab,
         "grammar": score if grammar is None else grammar,
         "content": score if content is None else content,
         "feedback_uz": "yaxshi", "ideal_ar": "جَوَاب", "done": done},
        ensure_ascii=False,
    )


@pytest.mark.asyncio
async def test_reply_mock_first_turn_and_grading(anthropic_mock):
    calls, handlers = anthropic_mock
    handlers.append(httpx.Response(200, json=_message(_mock_json(score=99, done=True))))
    out, _ = await tutor.reply_mock(name="N", level="A2", mock_id="haydovchi", history=[], known=[])
    assert out.score == -1 and out.done is False and out.feedback_uz == ""
    assert out.vocab == out.grammar == out.content == -1

    handlers.append(httpx.Response(200, json=_message(_mock_json(score=140, done=False))))
    hist = [{"role": "assistant", "content": "q"}, {"role": "user", "content": "a"}]
    out, _ = await tutor.reply_mock(name="N", level="A2", mock_id="haydovchi", history=hist, known=[])
    assert out.score == 100, "ball 0-100 oralig'ida qisqartiriladi"
    assert out.done is False

    # Umumiy ball — mezonlar o'rtachasi (model bergan score emas)
    handlers.append(httpx.Response(200, json=_message(_mock_json(score=10, vocab=90, grammar=60, content=75))))
    out, _ = await tutor.reply_mock(name="N", level="A2", mock_id="haydovchi", history=hist, known=[])
    assert (out.vocab, out.grammar, out.content, out.score) == (90, 60, 75, 75)

    handlers.append(httpx.Response(200, json=_message(_mock_json(score=50, done=False))))
    hist = [{"role": "assistant", "content": "q"}, {"role": "user", "content": "a"}] * tutor.MOCK_QUESTIONS
    out, _ = await tutor.reply_mock(name="N", level="A2", mock_id="haydovchi", history=hist, known=[])
    assert out.done is True, "savollar tugagach kod yakunlaydi"


@pytest.mark.asyncio
async def test_reply_mock_unknown_id(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "anthropic_api_key", "k")
    with pytest.raises(tutor.TutorUnavailable):
        await tutor.reply_mock(name="N", level="A2", mock_id="yoq", history=[], known=[])


def test_mock_overall_and_catalog():
    assert tutor.mock_overall(90, 60, 75) == 75
    assert tutor.mock_overall(90, 60, 75, 95) == 80
    assert tutor.mock_overall(-1, -1, -1) == 0
    assert len(tutor.MOCKS) == 20
    assert len({m["id"] for m in tutor.MOCKS}) == 20
    assert all(m["min_level"] in ("A0", "A1", "A2", "B1", "B2") for m in tutor.MOCKS)
    assert "vocab" in tutor.MOCK_RULES and "grammar" in tutor.MOCK_RULES and "content" in tutor.MOCK_RULES


def test_chat_reply_schema_has_answer_uz():
    assert "answer_uz" in tutor.TutorReply.model_fields
    assert tutor.TutorReply.model_fields["answer_uz"].default == ""
