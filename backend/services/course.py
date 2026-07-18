"""Curriculum v2 kurs yo'li — jonli dashboard va Lessons sahifasi uchun (K4).

v1 (services/content.py, eski 19 dars) o'rniga endi shu modul ishlatiladi:
darslar content/curriculum.json tartibida, faqat KONTENTI YOZILGAN darslar
(written_lesson_ids) "ochiladi". XP/streak/SRS Progress orqali saqlanib qoladi.
"""

from services.curriculum import (
    load_curriculum,
    load_lesson_v2,
    lesson_order,
    written_lesson_ids,
)

# Modul ko'rinishi: module_id -> (o'zbekcha sarlavha, arabcha sarlavha)
MODULE_META: dict[str, tuple[str, str]] = {
    # A0
    "letters": ("Harflar", "الحُرُوف"),
    "harakat": ("Harakatlar", "الحَرَكات"),
    "reading": ("O'qish qoidalari", "القِراءة"),
    "pronunciation": ("Talaffuz", "النُّطق"),
    "roots-intro": ("O'zaklar bilan tanishuv", "الجُذُور"),
    "workshop": ("Amaliy ustaxona", "الوَرْشة"),
    # A1
    "nominal-sentence": ("Ismli gaplar", "الجُملة الاسميّة"),
    "past-tense": ("O'tgan zamon", "الماضي"),
    "present-tense": ("Hozirgi zamon", "المُضارع"),
    "noun-system": ("Ot tizimi", "نِظام الاسم"),
    "daily-life": ("Kundalik hayot", "الحَياة اليوميّة"),
    # A2
    "verb-forms": ("Fe'l boblari", "أوزان الفِعل"),
    "weak-verbs": ("Illatli fe'llar", "الأفعال المُعتلّة"),
    "grammar-ext": ("Grammatika (kengaytma)", "النَّحو"),
    "saudi": ("Saudiya moduli", "السُّعوديّة"),
    "skills": ("Ko'nikmalar", "المَهارات"),
    # B1
    "adv-grammar": ("Yuqori grammatika", "النَّحو المُتقدّم"),
    "vocab": ("Lug'at boyligi", "المُفردات"),
    "quran-hadith": ("Qur'on va hadis", "القُرآن والحَديث"),
    "review": ("Umumiy takror", "المُراجعة"),
    # umumiy
    "exam": ("Daraja imtihoni", "الامتِحان"),
}

LEVELS = ["A0", "A1", "A2", "B1"]


def module_title(module_id: str) -> tuple[str, str]:
    return MODULE_META.get(module_id, (module_id.replace("-", " ").title(), ""))


def level_of(lesson_id: str) -> str:
    return load_curriculum().get(lesson_id, {}).get("level", "A0")


def written_course_ids() -> list[str]:
    """Kontenti yozilgan darslar — curriculum tartibida (imtihon type tashqari)."""
    written = written_lesson_ids()
    cur = load_curriculum()
    return [
        lid
        for lid in lesson_order()
        if lid in written and cur[lid]["type"] == "lesson"
    ]


def _level_start_index(level: str) -> int:
    """curriculum.json'da shu daraja boshlanadigan indeks."""
    order = lesson_order()
    for i, lid in enumerate(order):
        if lid.startswith(level.lower() + "-"):
            return i
    return 0


def start_lesson_for(level: str) -> str:
    """Daraja uchun boshlang'ich dars. Agar shu darajaning kontenti hali
    yozilmagan bo'lsa (A1/A2/B1), yozilgan eng birinchi darsga qaytadi —
    shunda onboarding'dan o'tgan har kim darsni boshlay oladi."""
    cur = load_curriculum()
    for lid in lesson_order():
        if lid.startswith(level.lower() + "-") and cur[lid]["type"] == "lesson":
            if lid in written_lesson_ids():
                return lid
            break
    written = written_course_ids()
    return written[0] if written else "a0-01"


def next_lesson(done: set[str], start_lesson: str | None) -> dict | None:
    """Foydalanuvchining start_lesson'idan boshlab birinchi tugatilmagan
    YOZILGAN darsni v1-shakldagi lug'atda qaytaradi (dashboard uchun).

    Agar oldinda yozilgan dars qolmagan bo'lsa (masalan, daraja kontenti hali
    tayyor emas) — butun yozilgan yo'ldan birinchi tugatilmaganini beradi, shunda
    hech kim boshi berk ko'chada qolmaydi.
    """
    order = lesson_order()
    written = written_course_ids()
    if not written:
        return None

    start = start_lesson if start_lesson in order else (written[0])
    start_idx = order.index(start) if start in order else 0

    # 1) start'dan oldinga qarab yozilgan tugatilmagan dars
    ahead = [lid for lid in written if order.index(lid) >= start_idx and lid not in done]
    # 2) bo'lmasa — umuman birinchi tugatilmagan yozilgan dars
    pick = ahead[0] if ahead else next((lid for lid in written if lid not in done), None)
    if pick is None:
        return None
    return _lesson_card(pick)


def _lesson_card(lesson_id: str) -> dict:
    cur = load_curriculum()
    meta = cur[lesson_id]
    mod = meta["module"]
    title_uz, title_ar = module_title(mod)
    # Modul ichidagi pozitsiya
    same_mod = [
        l for l in lesson_order()
        if cur[l]["module"] == mod and cur[l]["level"] == meta["level"]
    ]
    pos = same_mod.index(lesson_id) + 1 if lesson_id in same_mod else 1
    return {
        "id": lesson_id,
        "title": meta["title_uz"],
        "module_title": title_uz,
        "module_ar": title_ar,
        "pos": pos,
        "count": len(same_mod),
    }


def count_vocab(lesson_id: str) -> int:
    """Darsdagi yangi so'zlar soni (statistika uchun)."""
    data = load_lesson_v2(lesson_id)
    return len(data.get("vocabulary", [])) if data else 0


def _level_name(level: str) -> str:
    return {
        "A0": "Boshlang'ich",
        "A1": "Elementar",
        "A2": "O'rta-quyi",
        "B1": "O'rta",
    }.get(level, level)


def _level_modules(level: str, done: set[str]) -> list[dict]:
    """Bitta darajaning dars modullari + qulf holati (imtihonsiz)."""
    cur = load_curriculum()
    order = lesson_order()
    written = written_lesson_ids()

    level_ids = [
        lid for lid in order
        if cur[lid]["level"] == level and cur[lid]["type"] == "lesson"
    ]
    written_seq = [lid for lid in level_ids if lid in written]

    seen_mods: list[str] = []
    for lid in level_ids:
        m = cur[lid]["module"]
        if m not in seen_mods:
            seen_mods.append(m)

    modules: list[dict] = []
    for m in seen_mods:
        m_ids = [lid for lid in level_ids if cur[lid]["module"] == m]
        title_uz, title_ar = module_title(m)

        lessons = []
        for lid in m_ids:
            meta = cur[lid]
            is_written = lid in written
            is_done = lid in done
            if lid in written_seq:
                i = written_seq.index(lid)
                unlocked = i == 0 or written_seq[i - 1] in done
            else:
                unlocked = False  # hali yozilmagan
            lessons.append(
                {
                    "id": lid,
                    "title": meta["title_uz"],
                    "type": meta["type"],
                    "done": is_done,
                    "unlocked": (unlocked or is_done) and is_written,
                    "available": is_written,
                }
            )

        modules.append(
            {
                "id": m,
                "title": title_uz,
                "arabic_title": title_ar,
                "available": any(l["available"] for l in lessons),
                "done_count": sum(1 for l in lessons if l["done"]),
                "total": len(lessons),
                "lessons": lessons,
            }
        )
    return modules


def course_all_levels(done: set[str], current_level: str = "A0") -> dict:
    """Darslar sahifasi — 4 daraja (A0/A1/A2/B1) alohida, har birida progress %.

    Har daraja: modullar, tugatilgan/jami darslar soni, foiz, kontent bor-yo'qligi.
    Foydalanuvchi qaysi darajada ekanini adashtirmasligi uchun.
    """
    cur = load_curriculum()
    order = lesson_order()
    written = written_lesson_ids()

    levels_out: list[dict] = []
    for lvl in LEVELS:
        lvl_lessons = [
            lid for lid in order
            if cur[lid]["level"] == lvl and cur[lid]["type"] == "lesson"
        ]
        total = len(lvl_lessons)
        done_n = sum(1 for lid in lvl_lessons if lid in done)
        has_written = any(lid in written for lid in lvl_lessons)
        percent = round(100 * done_n / total) if total else 0

        levels_out.append(
            {
                "level": lvl,
                "name": _level_name(lvl),
                "available": has_written,
                "done": done_n,
                "total": total,
                "percent": percent,
                "modules": _level_modules(lvl, done) if has_written else [],
            }
        )

    return {"current_level": current_level, "levels": levels_out}
