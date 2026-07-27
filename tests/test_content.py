"""Kontent yaxlitligi — 156 dars, imtihon poollari, audio havolalari.

Bu testlar deploy'dan oldin buzuq kontentni ushlaydi: validator xatolari,
yo'q audio fayllar, kirill harflarining lotin matniga sizib kirishi.
"""

import json
import re
from pathlib import Path

import pytest

from services.curriculum import load_curriculum, lesson_file, written_lesson_ids
from services.exam import load_pool
from services.lesson_schema import validate_lesson

ROOT = Path(__file__).resolve().parent.parent
AUDIO_DIR = ROOT / "webapp" / "public" / "audio"
CYRILLIC = re.compile(r"[Ѐ-ӿ]")

WRITTEN = sorted(written_lesson_ids())
CURRICULUM = load_curriculum()


def test_curriculum_has_all_four_levels():
    levels = {m["level"] for m in CURRICULUM.values()}
    assert levels == {"A0", "A1", "A2", "B1"}


def test_every_written_lesson_is_in_curriculum():
    unknown = [lid for lid in WRITTEN if lid not in CURRICULUM]
    assert unknown == []


@pytest.mark.parametrize("lesson_id", WRITTEN)
def test_lesson_passes_validator(lesson_id):
    data = json.loads(lesson_file(lesson_id).read_text(encoding="utf-8"))
    errors, _ = validate_lesson(data, CURRICULUM[lesson_id], set(CURRICULUM))
    assert errors == [], f"{lesson_id}: {errors}"


@pytest.mark.parametrize("lesson_id", WRITTEN)
def test_lesson_has_no_cyrillic_leak(lesson_id):
    """Lotin matniga kirill harfi tushmasin ('zamonда' kabi)."""
    text = lesson_file(lesson_id).read_text(encoding="utf-8")
    found = re.findall(r"\S*[Ѐ-ӿ]+\S*", text)
    assert found == [], f"{lesson_id}: {found[:5]}"


@pytest.mark.parametrize("level", ["A0", "A1", "A2", "B1"])
def test_exam_pool_has_no_cyrillic_leak(level):
    text = json.dumps(load_pool(level), ensure_ascii=False)
    found = re.findall(r"\S*[Ѐ-ӿ]+\S*", text)
    assert found == [], f"{level}: {found[:5]}"


@pytest.mark.parametrize("lesson_id", WRITTEN)
def test_lesson_prerequisites_exist(lesson_id):
    data = json.loads(lesson_file(lesson_id).read_text(encoding="utf-8"))
    missing = [p for p in data.get("prerequisites", []) if p not in CURRICULUM]
    assert missing == [], f"{lesson_id}: {missing}"


@pytest.mark.parametrize("lesson_id", WRITTEN)
def test_mcq_answer_is_among_options(lesson_id):
    """Javob variantlar ichida bo'lmasa — savolni yechib bo'lmaydi."""
    data = json.loads(lesson_file(lesson_id).read_text(encoding="utf-8"))
    bad = [
        t["q_uz"][:40]
        for t in data["micro_test"]
        if t["type"] == "mcq" and t["answer"] not in t["options"]
    ]
    assert bad == [], f"{lesson_id}: {bad}"


@pytest.mark.parametrize("level", ["A0", "A1", "A2", "B1"])
def test_exam_pool_shape(level):
    pool = load_pool(level)
    assert pool is not None, f"{level} pool topilmadi"
    cfg = pool["config"]
    for section in ("reading", "listening", "writing", "speaking", "passages"):
        need = cfg.get(section, 0)
        have = len(pool.get(section, []))
        assert have >= need, f"{level}.{section}: {have} ta bor, {need} kerak"


@pytest.mark.parametrize("level", ["A0", "A1", "A2", "B1"])
def test_exam_has_exactly_one_fourth_section(level):
    """4-bo'lim yo gapirish, yo matn — ikkalasi birdan bo'lmaydi."""
    cfg = load_pool(level)["config"]
    assert bool(cfg.get("speaking")) != bool(cfg.get("passages")), (
        f"{level}: speaking={cfg.get('speaking')} passages={cfg.get('passages')}"
    )


@pytest.mark.parametrize("level", ["A0", "A1", "A2", "B1"])
def test_exam_pool_audio_files_exist(level):
    pool = load_pool(level)
    missing = [
        q["audio"]
        for section in ("reading", "listening", "speaking")
        for q in pool.get(section, [])
        if q.get("audio") and not (AUDIO_DIR / q["audio"]).exists()
    ]
    assert missing == [], f"{level}: yo'q audio {missing}"


@pytest.mark.parametrize("level", ["A2", "B1"])
def test_passages_are_well_formed(level):
    """Har matn: arabcha matn + kamida 2 ta MCQ, javob variantlar ichida."""
    for p in load_pool(level).get("passages", []):
        assert p["id"] and p["title_uz"], f"{level}: id/sarlavha yo'q"
        assert re.search(r"[؀-ۿ]", p["text_ar"]), f"{p['id']}: arabcha matn yo'q"
        assert len(p["text_ar"]) >= 120, f"{p['id']}: matn juda qisqa"
        assert len(p["questions"]) >= 2, f"{p['id']}: savol kam"
        for q in p["questions"]:
            assert q["answer"] in q["options"], f"{p['id']}: {q['q_uz'][:30]}"
            assert len(set(q["options"])) == len(q["options"]), (
                f"{p['id']}: takroriy variant"
            )


@pytest.mark.parametrize("level", ["A2", "B1"])
def test_passage_ids_unique(level):
    ids = [p["id"] for p in load_pool(level).get("passages", [])]
    assert len(set(ids)) == len(ids), f"{level}: takroriy matn id {ids}"


@pytest.mark.parametrize("level", ["A0", "A1", "A2", "B1"])
def test_exam_pool_mcq_answers_valid(level):
    pool = load_pool(level)
    bad = [
        q.get("q_uz", "")[:40]
        for section in ("reading", "listening")
        for q in pool.get(section, [])
        if q.get("options") and q["answer"] not in q["options"]
    ]
    assert bad == [], f"{level}: {bad}"


def test_lesson_audio_references_exist():
    """Darslardagi audio havolalar haqiqiy fayllarga ishora qilsin."""
    missing = []
    for lesson_id in WRITTEN:
        data = json.loads(lesson_file(lesson_id).read_text(encoding="utf-8"))
        refs = [v.get("audio") for v in data["vocabulary"]]
        refs += [h.get("audio") for h in data.get("hejazi", [])]
        refs.append((data.get("skills", {}).get("listening") or {}).get("audio"))
        for ref in refs:
            if ref and not (AUDIO_DIR / ref).exists():
                missing.append(f"{lesson_id}:{ref}")
    assert missing == [], missing[:10]
