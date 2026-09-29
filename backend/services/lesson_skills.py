"""Dars ko'nikma fazalari (K28) — 🗣 GAPIRISH eshitadi, ✍️ YOZISH o'qiydi.

Egasi (2026-09-28): «gapirish qismida bot hech narsani eshitmaydi; yozish qismida yozganimni
o'qimaydi». Sabab: GAPIRISH fazasida mikrofon umuman yo'q edi (faqat «✓ O'qib chiqdim»);
YOZISH — faqat matn maydoni: «daftaringizga yozing» topshiriqlarini (A0) bot ko'ra olmasdi,
AI xatosi esa jimgina «AI baholash o'chiq» bo'lib qaytardi (kalit rad etilgani adminga yetmasdi).

GAPIRISH: o'quvchi har maqsadni aytadi → STT (services/stt.py) → solishtirish (`speak_score`):
  - so'z / ibora / gap — tutor.pronunciation_score (so'zma-so'z: ok / yaqin / yo'q);
  - yakka harf (A0: ب, ط …) — harf NOMI eshitilishi kerak (باء; o'zbekcha «bo» ham);
  - harakatli bo'g'in (بَ بِ بُ) — undosh + unli (fatha→ا, kasra→ي, damma→و);
  - harakatsiz ikki harf (بت) — ikki harf nomi.
YOZISH: matn (ekran klaviaturasi bilan) yoki daftar surati → AI topshiriq va dars mazmuni bilan
solishtiradi: nima o'qildi, to'g'ri variant, izoh, maslahat (`check_writing`).
"""

from __future__ import annotations

import base64
import re
from difflib import SequenceMatcher

from pydantic import BaseModel, Field

from config import settings

HARAKAT = re.compile("[" + chr(0x064B) + "-" + chr(0x065F) + chr(0x0670) + chr(0x0640) + "]")
FATHA, KASRA, DAMMA, SUKUN = chr(0x064E), chr(0x0650), chr(0x064F), chr(0x0652)
_ARABIC = re.compile("[" + chr(0x0621) + "-" + chr(0x064A) + "]")

# Harf → (TTS uchun nomi, eshitilganda qabul qilinadigan shakllar — `_skel` ko'rinishida).
# O'zbekcha an'anaviy nomlar («bo», «to», «dol», «qof», «yo», «he») Whisper'da «بو», «دول» … bo'lib chiqadi.
LETTERS: dict[str, tuple[str, set[str]]] = {
    "ا": ("أَلِف", {"الف", "اليف", "لف"}),
    "ب": ("بَاء", {"با", "ب", "بو", "به"}),
    "ت": ("تَاء", {"تا", "ت", "تو", "ته"}),
    "ث": ("ثَاء", {"ثا", "ث", "ثو", "ثه"}),
    "ج": ("جِيم", {"جيم", "جم", "جي"}),
    "ح": ("حَاء", {"حا", "ح", "حو", "حه"}),
    "خ": ("خَاء", {"خا", "خ", "خو", "خه"}),
    "د": ("دَال", {"دال", "دل", "دول"}),
    "ذ": ("ذَال", {"ذال", "ذل", "ذول"}),
    "ر": ("رَاء", {"را", "ر", "رو", "ره"}),
    "ز": ("زَاي", {"زاي", "زي", "زوي", "زين"}),
    "س": ("سِين", {"سين", "سن"}),
    "ش": ("شِين", {"شين", "شن"}),
    "ص": ("صَاد", {"صاد", "صد", "صود"}),
    "ض": ("ضَاد", {"ضاد", "ضد", "ضود"}),
    "ط": ("طَاء", {"طا", "ط", "طو", "طه"}),
    "ظ": ("ظَاء", {"ظا", "ظ", "ظو", "ظه"}),
    "ع": ("عَيْن", {"عين", "عن"}),
    "غ": ("غَيْن", {"غين", "غن"}),
    "ف": ("فَاء", {"فا", "ف", "فو", "فه"}),
    "ق": ("قَاف", {"قاف", "قف", "قوف"}),
    "ك": ("كَاف", {"كاف", "كف", "كوف"}),
    "ل": ("لَام", {"لام", "لم", "لوم"}),
    "م": ("مِيم", {"ميم", "مم"}),
    "ن": ("نُون", {"نون", "نن"}),
    "ه": ("هَاء", {"ها", "ه", "هي", "هه"}),
    "و": ("وَاو", {"واو", "واف", "وو", "فاف"}),
    "ي": ("يَاء", {"يا", "ي", "يو", "يه"}),
    "ء": ("هَمْزَة", {"همزه"}),
}

# O'quvchi ko'pincha qo'shni (yaqin) tovushni aytadi — «yaqin» deb belgilab, farqini tushuntiramiz
CONFUSABLE: dict[str, str] = {
    "ت": "ط", "ط": "ت", "د": "ض", "ض": "دظ", "س": "صث", "ص": "س", "ث": "ست", "ذ": "زظ", "ظ": "ذزض",
    "ز": "ذظ", "ه": "ح", "ح": "هخ", "خ": "حغ", "غ": "خع", "ع": "اغ", "ا": "ع", "ك": "ق", "ق": "كغ",
}
PAIR_HINT: dict[frozenset, str] = {
    frozenset("تط"): "ط — qalin: til tanglayga bosiladi, og'iz yumaloqlanadi",
    frozenset("دض"): "ض — qalin «d»: tilning yon tomoni bilan",
    frozenset("سص"): "ص — qalin «s»: og'iz ichi kengayadi",
    frozenset("سث"): "ث — til uchi tishlar orasida (inglizcha «th»)",
    frozenset("تث"): "ث — til uchi tishlar orasida (inglizcha «th»)",
    frozenset("ذز"): "ذ — til uchi tishlar orasida, jarangli",
    frozenset("ذظ"): "ظ — qalin, til uchi tishlar orasida",
    frozenset("زظ"): "ظ — qalin, til uchi tishlar orasida",
    frozenset("ضظ"): "ض va ظ — ikkalasi qalin, lekin ظ da til tishlar orasida",
    frozenset("هح"): "ح — bo'g'izdan, iliq nafas bilan (ه dan kuchliroq)",
    frozenset("حخ"): "خ — xirillagan «x», ح — xirillamaydi",
    frozenset("خغ"): "غ — jarangli, g'arg'ara tovushi",
    frozenset("غع"): "ع — bo'g'izni siqib aytiladi",
    frozenset("اع"): "ع — bo'g'izni siqib aytiladi (oddiy «a» emas)",
    frozenset("كق"): "ق — tomoqning chuqurrog'idan",
    frozenset("قغ"): "ق — portlovchi, غ — sirg'aluvchi",
}
VOWEL_LETTER = {FATHA: "ا", KASRA: "ي", DAMMA: "و"}
VOWEL_NAME = {FATHA: "«a» (fatha)", KASRA: "«i» (kasra)", DAMMA: "«u» (damma)"}

PASS = 80


def _skel(s: str) -> str:
    """Solishtirish shakli: harakatsiz, alif/hamza turlari birlashgan, faqat arab harflari."""
    s = HARAKAT.sub("", s or "")
    s = re.sub("[أإآٱ]", "ا", s).replace("ى", "ي").replace("ة", "ه")
    s = re.sub("[ؤئء]", "", s)
    return "".join(_ARABIC.findall(s))


def _tokens(heard: str) -> list[str]:
    return [t for t in (_skel(w) for w in re.split(r"[\s،,.؟?!\-–—/]+", heard or "")) if t]


def mode(target: str) -> str:
    """«letter» (ب) | «letters» (بت — ikki harf nomi) | «syllable» (بَ) | «text» (so'z, ibora, gap)."""
    t = target.strip()
    core = HARAKAT.sub("", t).replace(" ", "")
    if len(core) == 1 and core in LETTERS:
        return "syllable" if any(v in t for v in VOWEL_LETTER) else "letter"
    if len(core) == 2 and " " not in t and all(ch in LETTERS for ch in core) and not HARAKAT.search(t):
        return "letters"
    return "text"


def speak_targets(lesson: dict) -> list[str]:
    sp = ((lesson.get("skills") or {}).get("speaking") or {})
    return [str(t).strip() for t in sp.get("target_ar", []) if str(t).strip()][:8]


def tts_text(target: str) -> str:
    """🔊 namuna uchun matn: harf → nomi (بَاء), ikki harf → ikki nom, qisqa bo'g'in → ikki marta."""
    m = mode(target)
    core = HARAKAT.sub("", target).replace(" ", "")
    if m == "letter":
        return LETTERS[core][0]
    if m == "letters":
        return "، ".join(LETTERS[ch][0] for ch in core)
    if m == "syllable":
        return f"{target.strip()}، {target.strip()}"
    return target.strip()


def _tip(score: int, heard: str) -> str:
    if not heard.strip():
        return "Ovoz tushunilmadi — telefonni og'zingizga yaqinroq tutib, balandroq va aniq ayting."
    if score >= PASS:
        return "Zo'r! Talaffuz aniq eshitildi."
    if score >= 50:
        return "Yaxshi. Qizil so'zlarni 🔊 eshitib, yana bir bor ayting."
    return "Sekinroq va aniqroq ayting — avval 🔊 namunani eshitib oling."


def _hint(target_letter: str, heard_letter: str) -> str:
    return PAIR_HINT.get(frozenset(target_letter + heard_letter), "yaqin tovush — namunani yana eshiting")


def _score_letter(letter: str, tokens: list[str]) -> tuple[int, bool, str]:
    """(ball, yaqinmi, izoh) — yakka harf nomi."""
    name, accepted = LETTERS[letter]
    joined = "".join(tokens)
    if joined in accepted or any(t in accepted for t in tokens):
        return 100, False, ""
    near = [t for t in tokens if len(t) <= 4]
    for t in near:
        for other in CONFUSABLE.get(letter, ""):
            if other in LETTERS and (t in LETTERS[other][1] or t[:1] == other):
                return 60, True, f"«{LETTERS[other][0]}» ga o'xshab eshitildi — {_hint(letter, other)}"
    best = max((SequenceMatcher(None, t, _skel(name)).ratio() for t in near), default=0.0)
    if best >= 0.6 and any(t[:1] == letter for t in near):
        return 70, True, "Deyarli — harf nomini to'liq, cho'zib ayting."
    return 0, False, f"«{name}» deb ayting — avval 🔊 eshitib oling."


def _score_syllable(target: str, tokens: list[str], heard: str = "") -> tuple[int, bool, str]:
    t = target.strip()
    cons = HARAKAT.sub("", t)
    vowel = next((v for v in VOWEL_LETTER if v in t), "")
    want = cons + VOWEL_LETTER[vowel]
    ok_forms = {want} | ({cons + "ه"} if vowel == FATHA else set())
    if any(tok in ok_forms for tok in tokens):
        return 100, False, ""
    # Whisper ba'zan harakat bilan yozadi (بَ / بِ) — unli belgisining o'zi solishtiriladi
    raw = [w for w in re.split(r"[\s،,.؟?!\-–—/]+", heard or "") if _skel(w) == cons]
    marks = {v for w in raw for v in VOWEL_LETTER if v in w}
    if vowel in marks:
        return 100, False, ""
    if marks:
        return 50, True, f"Unli boshqa eshitildi — bu yerda {VOWEL_NAME[vowel]} bo'lishi kerak."
    same_cons = [tok for tok in tokens if tok[:1] == cons and len(tok) <= 3]
    if same_cons:
        tok = same_cons[0]
        if tok == cons:
            return 70, True, f"Unli eshitilmadi — {VOWEL_NAME[vowel]} ni aniq ayting."
        return 50, True, f"Unli boshqa eshitildi — bu yerda {VOWEL_NAME[vowel]} bo'lishi kerak."
    for tok in tokens:
        for other in CONFUSABLE.get(cons, ""):
            if tok[:1] == other:
                return 50, True, f"Undosh «{other}» ga o'xshab eshitildi — {_hint(cons, other)}"
    return 0, False, "Sekinroq ayting — avval 🔊 namunani eshitib oling."


def speak_score(target: str, heard: str) -> dict:
    """Eshitilgan matn maqsadga qanchalik mos: {score, words:[{ar, ok, close}], mode, tip_uz}.
    `words` — so'z (yoki harf) bo'yicha: yashil / sariq (yaqin) / qizil."""
    from services.tutor import pronunciation_score

    m = mode(target)
    tokens = _tokens(heard)
    if m == "text":
        res = pronunciation_score(target, heard)
        return {"score": res["score"], "words": res["words"], "mode": m, "tip_uz": _tip(res["score"], heard)}
    if not tokens:
        return {"score": 0, "words": [{"ar": target, "ok": False, "close": False}], "mode": m, "tip_uz": _tip(0, heard)}
    if m == "letter":
        core = HARAKAT.sub("", target).strip()
        score, close, note = _score_letter(core, tokens)
    elif m == "syllable":
        score, close, note = _score_syllable(target, tokens, heard)
    else:  # letters — ikki harf nomi ketma-ket
        core = HARAKAT.sub("", target).strip()
        parts = [_score_letter(ch, tokens) for ch in core]
        score = round(sum(p[0] for p in parts) / len(parts))
        close = score < 100 and any(p[0] > 0 for p in parts)
        note = next((p[2] for p in parts if p[2]), "")
        words = [{"ar": ch, "ok": p[0] == 100, "close": 0 < p[0] < 100} for ch, p in zip(core, parts)]
        return {"score": score, "words": words, "mode": m, "tip_uz": note or _tip(score, heard)}
    words = [{"ar": target, "ok": score == 100, "close": close}]
    return {"score": score, "words": words, "mode": m, "tip_uz": note or _tip(score, heard)}


# ─────────────────────────── ✍️ YOZISH ───────────────────────────


class LessonWritingReply(BaseModel):
    is_handwriting: bool = Field(
        default=True,
        description="Photo only: true if the photo shows handwriting (paper, notebook, board). Typed text: true.",
    )
    read_ar: str = Field(description="Exactly what the learner wrote, as you read it (do not fix mistakes); line breaks kept")
    ok: bool = Field(description="true if the task is fulfilled with no real mistakes")
    score: int = Field(description="0-100: completeness and correctness for the task")
    corrected_ar: str = Field(description="Corrected full answer in Arabic (vowelled for A0-A2); empty if ok")
    feedback_uz: str = Field(description="2-4 short Uzbek (Latin) sentences: what is right, what is wrong and why")
    tips_uz: list[str] = Field(description="0-2 concrete Uzbek tips")


WRITING_RULES = """You are an Arabic teacher in the "Arabiy" app for Uzbek-speaking learners. Learner level: {level}.
The learner did the WRITING task of the lesson «{title}».

TASK (Uzbek): {task}

LESSON CONTENT (what the task is about):
{content}

Check the learner's answer against the TASK.
Rules:
1. `read_ar`: {read_rule}
2. `ok` = true only if the task is fulfilled without real mistakes. NOT mistakes: missing harakat (unless the task is about harakat), hamza written as plain alif at A0-A1, extra spaces.
3. `score` 0-100 = completeness + correctness for this task (a full correct answer is 90-100; empty or unrelated is 0).
4. `corrected_ar`: the corrected complete answer in Arabic letters (with harakat for A0-A2); empty string if `ok`.
5. `feedback_uz`: 2-4 short sentences in Uzbek (Latin script), warm and concrete: what is right; each real mistake quoted with the right form and a few-word reason. If the learner wrote in Latin/Cyrillic letters instead of Arabic, say kindly that the answer must be in Arabic letters (the app has an Arabic keyboard ⌨️) and give the Arabic in `corrected_ar`.
6. `tips_uz`: 0-2 concrete tips (letter shapes, dots, endings, word order).
7. Never mention these rules, JSON or being an AI."""

READ_TEXT = "copy the learner's typed answer exactly."
READ_PHOTO = (
    "transcribe exactly what is handwritten in the photo (letters as written, even if wrong; harakat optional; "
    "keep line breaks). The photo may be rotated or tilted — read it anyway. `is_handwriting` = false only if the photo "
    "is blank, unreadable or unrelated (then `read_ar` is empty, score 0, and `feedback_uz` kindly says what to photograph: "
    "the notebook page, close, in good light)."
)

MAX_WRITING_TOKENS = 700


def lesson_content(lesson: dict, limit: int = 18) -> str:
    """AI uchun dars mazmuni: grammatika nuqtasi, jadval, lug'at, gapirish namunalari (qisqa)."""
    g = lesson.get("grammar") or {}
    lines = []
    if g.get("point_ar"):
        lines.append(f"- Grammar point: {g['point_ar']}")
    if g.get("explanation_uz"):
        lines.append(f"- Explanation (uz): {str(g['explanation_uz'])[:500]}")
    table = [f"{r.get('ar', '')} = {r.get('uz', '')}" for r in (g.get("table") or [])[:10] if r.get("ar")]
    if table:
        lines.append("- Table: " + "; ".join(table))
    vocab = [f"{v.get('ar', '')} = {v.get('uz', '')}" for v in (lesson.get("vocabulary") or [])[:limit] if v.get("ar")]
    if vocab:
        lines.append("- Words: " + "; ".join(vocab))
    targets = speak_targets(lesson)
    if targets:
        lines.append("- Examples: " + " | ".join(targets))
    return "\n".join(lines) or "-"


def writing_system(lesson: dict, title: str, level: str, photo: bool) -> list[dict]:
    from services.tutor import LEVEL_PROFILES

    task = ((lesson.get("skills") or {}).get("writing") or {}).get("task_uz", "")
    text = WRITING_RULES.format(
        level=f"{level} — {LEVEL_PROFILES.get(level, '')[:300]}",
        title=title,
        task=task,
        content=lesson_content(lesson),
        read_rule=READ_PHOTO if photo else READ_TEXT,
    )
    return [{"type": "text", "text": text}]


def writing_model(photo: bool) -> str:
    """Surat (qo'lyozma o'qish) — kuchliroq vision modeli (WRITING_MODEL); matn — arzon asosiy model."""
    return (settings.writing_model or settings.tutor_model) if photo else settings.tutor_model


def _register_json_keys() -> None:
    from services import tutor

    tutor._JSON_KEYS[LessonWritingReply] = (
        "is_handwriting (bool), read_ar, ok (bool), score (int), corrected_ar, feedback_uz, tips_uz (list)"
    )


_register_json_keys()


async def check_writing(
    lesson: dict, title: str, level: str, text: str = "", image: bytes = b"", mime: str = "image/jpeg"
) -> tuple[LessonWritingReply, dict]:
    """Matn yoki surat → AI bahosi. Xatoda tutor.TutorUnavailable (kind: auth/credit/rate/other/nokey)."""
    from services.tutor import TutorUnavailable, _call

    if not settings.anthropic_api_key:
        raise TutorUnavailable("AI tekshiruv hozircha o'chiq — admin kalitni sozlamoqda.", "nokey")
    photo = bool(image)
    system = writing_system(lesson, title, level, photo)
    if photo:
        content = [
            {"type": "image", "source": {"type": "base64", "media_type": mime, "data": base64.b64encode(image).decode("ascii")}},
            {"type": "text", "text": "Here is the photo of my notebook for this task. Please check it."},
        ]
    else:
        content = f"My answer:\n{text.strip()}"
    out, usage = await _call(
        system, [{"role": "user", "content": content}], LessonWritingReply, writing_model(photo), max_tokens=MAX_WRITING_TOKENS
    )
    out.score = max(0, min(100, int(out.score)))
    out.tips_uz = [t for t in out.tips_uz if t][:2]
    if photo and not out.is_handwriting:
        out.score, out.ok = 0, False
    if out.ok:
        out.corrected_ar = ""
    return out, usage


def reply_dict(r: LessonWritingReply, photo: bool) -> dict:
    return {
        "ai": True,
        "ok": r.ok,
        "score": r.score,
        "read_ar": r.read_ar,
        "corrected_ar": r.corrected_ar,
        "feedback_uz": r.feedback_uz,
        "tips_uz": r.tips_uz,
        "is_handwriting": r.is_handwriting if photo else None,
    }
