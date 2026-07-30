"""Kurs yo'li: daraja tablari, modul qulflari, keyingi dars."""

from services.course import LEVELS, course_all_levels, next_lesson, start_lesson_for
from services.curriculum import written_lesson_ids

WRITTEN = written_lesson_ids()


def test_all_levels_present_in_tabs():
    data = course_all_levels(set(), current_level="A0")
    assert [lv["level"] for lv in data["levels"]] == LEVELS


def test_written_levels_are_available():
    data = course_all_levels(set(), current_level="A0")
    by_level = {lv["level"]: lv for lv in data["levels"]}
    for level in ("A0", "A1", "A2", "B1"):
        assert by_level[level]["available"] is True, f"{level} ochiq bo'lishi kerak"
        assert by_level[level]["total"] > 0


def test_percent_zero_when_nothing_done():
    data = course_all_levels(set(), current_level="A0")
    assert all(lv["percent"] == 0 for lv in data["levels"])


def test_percent_reflects_completion():
    a0 = sorted(lid for lid in WRITTEN if lid.startswith("a0-"))
    half = len(a0) // 2
    data = course_all_levels(set(a0[:half]), current_level="A0")
    level_a0 = next(lv for lv in data["levels"] if lv["level"] == "A0")
    assert level_a0["done"] == half
    assert level_a0["percent"] == round(half / len(a0) * 100)


def test_full_completion_gives_100_percent():
    a0 = {lid for lid in WRITTEN if lid.startswith("a0-")}
    data = course_all_levels(a0, current_level="A0")
    level_a0 = next(lv for lv in data["levels"] if lv["level"] == "A0")
    assert level_a0["percent"] == 100


def test_first_lesson_of_each_level_is_reachable():
    """Har daraja o'z birinchi darsidan mustaqil boshlanadi (qulf zanjiri
    darajalar bo'ylab emas, daraja ICHIDA)."""
    data = course_all_levels(set(), current_level="A0")
    for lv in data["levels"]:
        if not lv["modules"]:
            continue
        first = lv["modules"][0]["lessons"][0]
        assert first["unlocked"] is True, f"{lv['level']} birinchi darsi qulflangan"


def test_second_lesson_locked_until_first_done():
    data = course_all_levels(set(), current_level="A0")
    lessons = data["levels"][0]["modules"][0]["lessons"]
    assert lessons[1]["unlocked"] is False

    data2 = course_all_levels({lessons[0]["id"]}, current_level="A0")
    lessons2 = data2["levels"][0]["modules"][0]["lessons"]
    assert lessons2[1]["unlocked"] is True


def test_start_lesson_for_each_level():
    """Kontenti bor daraja o'z darsidan boshlanadi; kontenti yo'q daraja
    (K15 da B2) yozilgan eng birinchi darsga qaytadi — hech kim boshi berk
    ko'chada qolmaydi."""
    for level in LEVELS:
        lid = start_lesson_for(level)
        assert lid in WRITTEN
        has_content = any(w.startswith(level.lower() + "-") for w in WRITTEN)
        if has_content:
            assert lid.lower().startswith(level.lower())
        else:
            assert lid == sorted(WRITTEN)[0] or lid.startswith("a0-")


def test_next_lesson_advances_along_path():
    start = start_lesson_for("A0")
    first = next_lesson(set(), start)
    assert first is not None
    assert first["id"] == start
    assert first["pos"] == 1

    second = next_lesson({start}, start)
    assert second is not None
    assert second["id"] != start
    assert second["pos"] == 2


def test_next_lesson_none_when_everything_done():
    assert next_lesson(set(WRITTEN), start_lesson_for("A0")) is None
