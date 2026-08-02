"""B2 darajasi — skelet (K15.1). Kontent yozilishidan oldingi kafolatlar.

Reja: docs/B2_PLAN.md. Bu testlar B2 darajasi tizimga TO'G'RI ulanganini
tekshiradi: kurikulum, modul tartibi, daraja ro'yxatlari, sertifikat/yutuq
nomlari va kontenti yo'q darajaga ko'tarilmaslik.
"""

from itertools import groupby

import pytest

from services import exam as ex
from services.certificate import LEVEL_NAMES
from services.course import LEVELS, MODULE_META, course_all_levels
from services.curriculum import load_curriculum, lesson_order, written_lesson_ids

CUR = load_curriculum()
B2 = [l for l in CUR.values() if l["level"] == "B2"]
B2_MODULES = [
    "nahw-adv",
    "sarf-adv",
    "balagha",
    "vocab-adv",
    "saudi-work",
    "skills-adv",
    "review",
    "exam",
]


# ── Kurikulum ──


def test_b2_has_fifty_lessons():
    assert len(B2) == 50, "B2 = 49 dars + 1 imtihon (docs/B2_PLAN.md)"


def test_last_b2_node_is_exam():
    assert CUR["b2-50"]["type"] == "exam"
    assert sum(1 for l in B2 if l["type"] == "lesson") == 49


def test_module_sizes_match_plan():
    ordered = [CUR[lid] for lid in lesson_order() if CUR[lid]["level"] == "B2"]
    runs = [(k, len(list(g))) for k, g in groupby(ordered, key=lambda l: l["module"])]
    assert runs == [
        ("nahw-adv", 10),
        ("sarf-adv", 6),
        ("balagha", 5),
        ("vocab-adv", 10),
        ("saudi-work", 5),
        ("skills-adv", 10),
        ("review", 3),
        ("exam", 1),
    ]


def test_every_b2_module_has_a_title():
    for m in B2_MODULES:
        assert m in MODULE_META, f"{m} uchun MODULE_META sarlavhasi yo'q"
        title_uz, title_ar = MODULE_META[m]
        assert title_uz and title_ar


def test_b2_ids_are_sequential():
    ids = [l["id"] for l in sorted(B2, key=lambda l: l["order"])]
    assert ids == [f"b2-{i:02d}" for i in range(1, 51)]


def test_harakat_level_is_real_text_mode():
    """B2 = real matnga o'tish: harakat faqat chalkash so'zlarda."""
    assert all(l["harakat_level"] == "ambiguous_only" for l in B2)


def test_hejazi_only_in_work_module():
    hejazi = {l["id"] for l in B2 if l["hejazi"]}
    assert hejazi == {"b2-32", "b2-33", "b2-34", "b2-35", "b2-36"}


def test_words_target_close_to_plan():
    total = sum(l["words_target"] for l in B2)
    assert 450 <= total <= 520, f"reja ~490 so'z, hozir {total}"


def test_prerequisites_chain():
    for l in B2:
        if l["order"] == 1:
            assert l["prerequisites"] == []
        else:
            assert l["prerequisites"] == [f"b2-{l['order'] - 1:02d}"]


# ── Daraja ro'yxatlari ──


def test_b2_in_level_lists():
    assert LEVELS == ["A0", "A1", "A2", "B1", "B2"]
    assert ex.LEVEL_ORDER == ["A0", "A1", "A2", "B1", "B2"]
    assert ex.next_level("B1") == "B2"
    assert ex.next_level("B2") is None


def test_certificate_has_b2_name():
    assert LEVEL_NAMES.get("B2")


def test_b2_badge_exists():
    from services.achievements import BADGE_BY_ID

    assert "level_b2" in BADGE_BY_ID


def test_lessons_page_shows_b2_tab():
    data = course_all_levels(set(), current_level="B1")
    by_level = {lv["level"]: lv for lv in data["levels"]}
    assert "B2" in by_level
    assert by_level["B2"]["total"] == 49  # imtihon tuguni sanalmaydi
    assert by_level["B2"]["name"] == "O'rta-yuqori"


# ── Kontent yozilmagan darajaga oid kafolatlar ──


def test_b2_marked_unavailable_until_content_written():
    """Kontent yo'q ekan «tayyorlanmoqda» ko'rinadi va modullar bo'sh."""
    written_b2 = {lid for lid in written_lesson_ids() if lid.startswith("b2-")}
    b2 = next(
        lv for lv in course_all_levels(set(), "A0")["levels"] if lv["level"] == "B2"
    )
    if not written_b2:
        assert b2["available"] is False
        assert b2["modules"] == []
    else:  # kontent yozilgach karta ko'rinadi
        assert b2["available"] is True


def test_exam_not_available_without_pool():
    """b2_pool.json yozilmagunicha B2 imtihoni boshlanmaydi."""
    if ex.load_pool("B2") is None:
        assert ex.exam_available("B2") is False


# ── B2 imtihon banki (K15.5) ──

POOL = ex.load_pool("B2")


def test_b2_pool_config_matches_plan():
    assert POOL is not None, "content/exams/b2_pool.json yo'q"
    assert POOL["config"] == {
        "reading": 12,
        "listening": 10,
        "writing": 3,
        "speaking": 0,
        "passages": 4,
        "minutes": 55,
    }


@pytest.mark.parametrize("section", ["reading", "listening", "writing", "passages"])
def test_b2_bank_is_three_times_the_exam(section):
    """Bank 3 barobar — uch marta TO'LIQ boshqa savollar bilan topshirish uchun."""
    need = POOL["config"][section]
    assert len(POOL[section]) >= need * 3, f"{section}: bank kichik"


def test_b2_listening_audio_files_exist():
    from config import BASE_DIR

    for item in POOL["listening"]:
        path = BASE_DIR / "webapp" / "public" / "audio" / item["audio"]
        assert path.exists(), f"audio yo'q: {item['audio']}"


def test_b2_answers_are_among_options():
    def check(items):
        for it in items:
            assert it["answer"] in it["options"]
            assert len(set(it["options"])) == len(it["options"])

    check(POOL["reading"])
    check(POOL["listening"])
    for p in POOL["passages"]:
        assert len(p["questions"]) == 3
        check(p["questions"])


def test_b2_exam_builds_and_is_full_size():
    exam = ex.build_exam("B2")
    cfg = POOL["config"]
    for section in ("reading", "listening", "writing", "passages"):
        assert len(exam[section]) == cfg[section]
    assert exam["minutes"] == 55
    assert ex.passage_questions(exam) == 12


def test_b2_retake_gives_different_questions():
    """24 soatdan keyingi qayta topshirishda savollar takrorlanmaydi."""
    from services.qbank import qhash

    first = ex.build_exam("B2")
    seen = {
        qhash(it)
        for s in ("reading", "listening", "writing", "passages")
        for it in first[s]
    }
    second = ex.build_exam("B2", seen=seen)
    for section in ("reading", "listening", "passages"):
        overlap = {qhash(i) for i in second[section]} & seen
        assert not overlap, f"{section}: takrorlangan savol bor"


def test_b2_exam_is_now_available():
    assert ex.exam_available("B2") is True


@pytest.mark.asyncio
async def test_b1_pass_does_not_promote_to_empty_b2(session, make_user):
    """B1 imtihonidan o'tgan foydalanuvchi kontenti yo'q B2 ga ko'tarilmaydi."""
    from db.models import Plan

    user = await make_user()
    plan = Plan(
        user_id=user.id,
        level="B1",
        target_level="B2",
        target_date="2027-01-01",
    )
    session.add(plan)
    await session.commit()

    nxt = ex.next_level("B1")
    has_content = bool(ex.level_lesson_ids(nxt))
    written_b2 = {lid for lid in written_lesson_ids() if lid.startswith("b2-")}
    assert has_content == bool(written_b2)
