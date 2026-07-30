"""A2+ o'qish bosqichlari va modul kartalarining bo'lak-bo'lak ko'rinishi (K14)."""

import pytest

from services.course import course_all_levels
from services.curriculum import written_lesson_ids
from services.reading import load_stages, passage_for, stage_list

LEVELS = ("A2", "B1")


@pytest.mark.parametrize("level", LEVELS)
def test_stages_exist(level):
    assert len(load_stages(level)) >= 10


@pytest.mark.parametrize("level", LEVELS)
def test_stage_lessons_are_written(level):
    written = written_lesson_ids()
    for st in load_stages(level):
        assert st["lesson_id"] in written, st["lesson_id"]
        assert st["lesson_id"].startswith(level.lower()), st["lesson_id"]


@pytest.mark.parametrize("level", LEVELS)
def test_stage_numbers_are_sequential(level):
    numbers = [s["stage"] for s in load_stages(level)]
    assert numbers == list(range(1, len(numbers) + 1))


@pytest.mark.parametrize("level", LEVELS)
def test_texts_get_longer(level):
    """Bosqichma-bosqich: oxirgi matn birinchisidan uzun."""
    stages = load_stages(level)
    assert stages[-1]["words"] > stages[0]["words"]


@pytest.mark.parametrize("level", LEVELS)
def test_questions_are_answerable(level):
    for st in load_stages(level):
        assert len(st["questions"]) >= 2, st["lesson_id"]
        for q in st["questions"]:
            assert q["answer"] in q["options"], (st["lesson_id"], q["q_uz"])
            assert len(set(q["options"])) == len(q["options"]), st["lesson_id"]


@pytest.mark.parametrize("level", LEVELS)
def test_audio_and_glossary_present(level):
    from pathlib import Path

    audio_dir = Path(__file__).resolve().parent.parent / "webapp" / "public" / "audio"
    for st in load_stages(level):
        assert st["glossary"], st["lesson_id"]
        assert (audio_dir / st["audio"]).exists(), st["audio"]


def test_passage_attached_to_lesson():
    p = passage_for("a2-01")
    assert p is not None
    assert p["level"] == "A2"
    assert p["stages_total"] == len(load_stages("A2"))


def test_a0_and_a1_have_no_passages():
    """O'qish moduli A2 dan boshlanadi (foydalanuvchi talabi)."""
    assert passage_for("a0-01") is None
    assert passage_for("a1-20") is None


def test_stage_list_is_lightweight():
    for row in stage_list("A2"):
        assert set(row) == {"stage", "lesson_id", "title_uz", "words"}


# ── Modul kartalari: kursda ikki joyda turgan modul ikki karta bo'ladi ──


def test_split_module_becomes_two_cards():
    a0 = next(
        lv for lv in course_all_levels(set(), "A0")["levels"] if lv["level"] == "A0"
    )
    ids = [m["id"] for m in a0["modules"]]
    assert "reading" in ids
    assert "reading-2" in ids, "a0-37 alohida kartada bo'lishi kerak"
    titles = {m["id"]: m["title"] for m in a0["modules"]}
    assert titles["reading-2"].endswith("(davomi)")


def test_module_cards_follow_course_order():
    """Karta ichidagi darslar kurs tartibida ketma-ket — qulf zanjiri bilan mos."""
    for lv in course_all_levels(set(), "A0")["levels"]:
        for mod in lv["modules"]:
            nums = [int(l["id"].split("-")[1]) for l in mod["lessons"]]
            assert nums == list(range(nums[0], nums[0] + len(nums))), mod["id"]


def test_first_lesson_of_each_card_locked_until_previous_card_done():
    """«(davomi)» kartasi oldingi darslar tugamaguncha qulflangan."""
    a0 = next(
        lv for lv in course_all_levels(set(), "A0")["levels"] if lv["level"] == "A0"
    )
    cont = next(m for m in a0["modules"] if m["id"] == "reading-2")
    assert cont["lessons"][0]["unlocked"] is False

    # Undan oldingi barcha A0 darslari tugatilsa — ochiladi
    lesson_id = cont["lessons"][0]["id"]
    n = int(lesson_id.split("-")[1])
    done = {f"a0-{i:02d}" for i in range(1, n)}
    a0_done = next(
        lv for lv in course_all_levels(done, "A0")["levels"] if lv["level"] == "A0"
    )
    cont2 = next(m for m in a0_done["modules"] if m["id"] == "reading-2")
    assert cont2["lessons"][0]["unlocked"] is True
