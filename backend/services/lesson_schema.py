"""Dars JSON sxemasi v2 (spec §10) — Pydantic modellari + chuqur validatsiya.

Ikkala joyda ishlatiladi:
- AI generator (structured output sxemasi sifatida)
- scripts/validate_content.py (kontentni tekshirish)
"""

import re
from typing import Literal

from pydantic import BaseModel, Field

# ── Yordamchi regexlar ──
ARABIC_LETTER = re.compile(r"[ء-ي]")
HARAKAT = re.compile(r"[ً-ْٰ]")
ARABIC_ANY = re.compile(r"[؀-ۿ]")

MICRO_TEST_TYPES = (
    "mcq",
    "fill_blank",
    "translate_uz_ar",
    "translate_ar_uz",
    "harakat",
    "dictation",
    "match_root",
    "build_word",
    "shadowing",
    "order_words",
)


class GrammarRow(BaseModel):
    ar: str
    uz: str
    form: str = ""


class Grammar(BaseModel):
    point_ar: str = ""
    explanation_uz: str = ""
    table: list[GrammarRow] = Field(default_factory=list)
    common_mistakes_uz: list[str] = Field(default_factory=list)


class DerivedWord(BaseModel):
    ar: str
    uz: str
    pattern: str = ""


class RootEntry(BaseModel):
    root: str  # "ك ت ب" (bo'shliq bilan)
    meaning_uz: str
    uz_cognates: list[str] = Field(default_factory=list)
    derived: list[DerivedWord] = Field(default_factory=list)


class VocabItem(BaseModel):
    ar: str
    translit: str
    uz: str
    root: str = ""
    pattern: str = ""
    pos: str = ""
    audio: str = ""
    example_ar: str = ""
    example_uz: str = ""
    srs: bool = True


class HejaziItem(BaseModel):
    msa_ar: str
    hejazi_ar: str
    translit: str
    uz: str
    audio: str = ""


class SkillQuestion(BaseModel):
    q_uz: str
    a: str


class ReadingSkill(BaseModel):
    text_ar: str = ""
    questions: list[SkillQuestion] = Field(default_factory=list)


class ListeningSkill(BaseModel):
    audio: str = ""
    transcript_ar: str = ""
    questions: list[SkillQuestion] = Field(default_factory=list)


class SpeakingSkill(BaseModel):
    task_uz: str = ""
    target_ar: list[str] = Field(default_factory=list)
    eval: str = "self_check"  # v1: self_check; keyin: azure_pronunciation


class WritingSkill(BaseModel):
    task_uz: str = ""
    eval: str = "ai_grammar"


class Skills(BaseModel):
    reading: ReadingSkill = Field(default_factory=ReadingSkill)
    listening: ListeningSkill = Field(default_factory=ListeningSkill)
    speaking: SpeakingSkill = Field(default_factory=SpeakingSkill)
    writing: WritingSkill = Field(default_factory=WritingSkill)


class MicroTestItem(BaseModel):
    """Barcha turlar uchun yagona model — tur talablari validate_lesson'da."""

    type: Literal[
        "mcq",
        "fill_blank",
        "translate_uz_ar",
        "translate_ar_uz",
        "harakat",
        "dictation",
        "match_root",
        "build_word",
        "shadowing",
        "order_words",
    ]
    q_uz: str = ""
    q_ar: str = ""
    options: list[str] = Field(default_factory=list)
    answer: str = ""  # mcq uchun ham matn (options ichidan) — indeks emas
    explain_uz: str = ""
    audio: str = ""
    root: str = ""
    pattern: str = ""
    words: list[str] = Field(default_factory=list)  # order_words banki


class SrsCard(BaseModel):
    type: Literal["word", "root", "pattern", "phrase"]
    front: str
    back: str
    deck: Literal["msa", "hejazi"] = "msa"


class LessonV2(BaseModel):
    id: str
    level: Literal["A0", "A1", "A2", "B1", "B2"]
    module: str
    order: int
    title_uz: str
    title_ar: str = ""
    can_do_uz: str
    duration_min: int = 30
    prerequisites: list[str] = Field(default_factory=list)
    harakat_level: Literal[
        "full", "new_words_only", "ambiguous_only", "none"
    ] = "full"
    hook_uz: str = ""
    grammar: Grammar = Field(default_factory=Grammar)
    roots: list[RootEntry] = Field(default_factory=list)
    vocabulary: list[VocabItem] = Field(default_factory=list)
    hejazi: list[HejaziItem] = Field(default_factory=list)
    skills: Skills = Field(default_factory=Skills)
    micro_test: list[MicroTestItem] = Field(default_factory=list)
    srs_cards: list[SrsCard] = Field(default_factory=list)


# ─────────────────────── Chuqur validatsiya ───────────────────────


def _has_harakat(word: str) -> bool:
    return bool(HARAKAT.search(word))


def _is_root_format(root: str) -> bool:
    """'ك ت ب' yoki 'ك-ت-ب' — 3-4 arab harfi."""
    letters = [p for p in re.split(r"[\s\-–]+", root.strip()) if p]
    return 2 <= len(letters) <= 4 and all(
        len(p) == 1 and ARABIC_LETTER.match(p) for p in letters
    )


def validate_lesson(
    data: dict,
    meta: dict | None = None,
    known_lesson_ids: set[str] | None = None,
) -> tuple[list[str], list[str]]:
    """(errors, warnings) qaytaradi. errors bo'sh bo'lsa — dars yaroqli."""
    errors: list[str] = []
    warnings: list[str] = []

    # 1. Sxema
    try:
        lesson = LessonV2.model_validate(data)
    except Exception as e:
        return [f"Sxema xatosi: {e}"], []

    # 2. Meta bilan moslik (curriculum.json'dagi yozuv)
    if meta:
        if lesson.id != meta["id"]:
            errors.append(f"id mos emas: {lesson.id} != {meta['id']}")
        if lesson.level != meta["level"]:
            errors.append(f"level mos emas: {lesson.level} != {meta['level']}")
        if lesson.harakat_level != meta.get("harakat_level", "full"):
            warnings.append(
                f"harakat_level meta bilan farq qiladi: {lesson.harakat_level}"
            )

    # 3. Prerequisite'lar mavjudligi
    if known_lesson_ids:
        for p in lesson.prerequisites:
            if p not in known_lesson_ids:
                errors.append(f"Noma'lum prerequisite: {p}")

    # 4. Lug'at
    words_target = (meta or {}).get("words_target", None)
    n_vocab = len(lesson.vocabulary)
    if words_target and n_vocab == 0:
        errors.append("Lug'at bo'sh, lekin meta so'z talab qiladi")
    if words_target and abs(n_vocab - words_target) > 4:
        warnings.append(f"So'z soni {n_vocab}, mo'ljal {words_target}")

    full_harakat = lesson.harakat_level in ("full", "new_words_only")
    for v in lesson.vocabulary:
        if not ARABIC_ANY.search(v.ar):
            errors.append(f"Lug'atda arabcha emas: {v.ar!r}")
            continue
        if full_harakat and not _has_harakat(v.ar) and len(v.ar.strip()) > 1:
            # Yakka harf kartalari (alifbo darslari) harakatsiz bo'lishi mumkin
            errors.append(f"Harakatsiz so'z (level={lesson.harakat_level}): {v.ar}")
        if v.root and not _is_root_format(v.root):
            errors.append(f"O'zak formati xato: {v.root!r} ({v.ar})")
        if not v.uz.strip():
            errors.append(f"Tarjimasiz so'z: {v.ar}")
        if not v.translit.strip():
            warnings.append(f"Transliteratsiyasiz: {v.ar}")

    # 5. O'zaklar
    for r in lesson.roots:
        if not _is_root_format(r.root):
            errors.append(f"O'zak formati xato: {r.root!r}")
        if not r.derived:
            warnings.append(f"O'zak yasalmalarsiz: {r.root}")
        for d in r.derived:
            if full_harakat and not _has_harakat(d.ar):
                warnings.append(f"Yasalma harakatsiz: {d.ar}")

    # 6. Mikro-test
    n_test = len(lesson.micro_test)
    if not 4 <= n_test <= 8:
        (errors if n_test < 3 else warnings).append(
            f"Mikro-test savollari: {n_test} (mo'ljal 5-7)"
        )
    for i, t in enumerate(lesson.micro_test, 1):
        tag = f"test#{i}({t.type})"
        if t.type == "mcq":
            if len(t.options) < 2:
                errors.append(f"{tag}: variantlar kam")
            elif t.answer not in t.options:
                errors.append(f"{tag}: answer options ichida emas")
        elif t.type in ("fill_blank", "translate_uz_ar", "translate_ar_uz",
                        "dictation", "harakat", "match_root"):
            if not t.answer.strip():
                errors.append(f"{tag}: answer bo'sh")
        elif t.type == "build_word":
            if not (t.root and t.pattern and t.answer):
                errors.append(f"{tag}: root/pattern/answer to'liq emas")
            elif not _is_root_format(t.root):
                errors.append(f"{tag}: o'zak formati xato: {t.root!r}")
        elif t.type == "order_words":
            if len(t.words) < 2 or not t.answer.strip():
                errors.append(f"{tag}: words/answer to'liq emas")
        if t.type == "dictation" and not t.audio:
            warnings.append(f"{tag}: audio ko'rsatilmagan")

    # 7. SRS kartalar
    if not lesson.srs_cards and lesson.vocabulary:
        warnings.append("SRS kartalar bo'sh")
    for c in lesson.srs_cards:
        if c.type in ("root",) and not _is_root_format(c.front):
            warnings.append(f"SRS root karta old tomoni: {c.front!r}")

    # 8. Hejazi deck belgilari
    for h in lesson.hejazi:
        if not ARABIC_ANY.search(h.hejazi_ar):
            errors.append(f"Hejazi arabcha emas: {h.hejazi_ar!r}")
    # Hijoziy iborani xato deck bilan qo'yish: karta matni darsning hejazi
    # ro'yxatidagi ibora bo'lsa-yu, deck 'msa' bo'lsa — ogohlantiramiz.
    # (MSA iboralari phrase turida bo'lishi mumkin, ular ogohlantirilmaydi.)
    hejazi_fronts = {h.hejazi_ar.strip() for h in lesson.hejazi}
    for c in lesson.srs_cards:
        if c.type == "phrase" and c.deck != "hejazi" and c.front.strip() in hejazi_fronts:
            warnings.append(f"hijoziy ibora deck=msa: {c.front!r} — hejazi bo'lishi kerak")

    # 9. Umumiy
    if not lesson.can_do_uz.strip():
        errors.append("can_do_uz bo'sh")
    if lesson.grammar.point_ar and not lesson.grammar.explanation_uz.strip():
        errors.append("Grammatika izohi (explanation_uz) bo'sh")

    return errors, warnings
