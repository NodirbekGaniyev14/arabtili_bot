"""K27 — yozma javob tekshiruvi (webapp/src/pages/v2/answerCheck.ts) node orqali.

O'quvchilar «to'g'ri javobim xato hisoblandi» deb yuborgan holatlar (#F107–#F117),
xato javoblar baribir rad etilishi va butun kontent: har yozma savolning namunasi
va `accept` yozuvlari o'z tekshiruvidan o'tishi.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
RUNNER = ROOT / "tests" / "js" / "answer_check_runner.cjs"
ESBUILD = ROOT / "webapp" / "node_modules" / "esbuild"

pytestmark = pytest.mark.skipif(
    not shutil.which("node") or not ESBUILD.exists(), reason="node yoki webapp/node_modules yo'q"
)


def run(cases: list[list]) -> list[dict]:
    r = subprocess.run(
        ["node", str(RUNNER)], input=json.dumps(cases), capture_output=True, text=True, encoding="utf-8"
    )
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def lat(answer, value, **opts):
    return ["latOk", answer, value, opts]


def ar(answer, value, **opts):
    return ["arOk", answer, value, opts]


# O'quvchi yozishi mumkin bo'lgan to'g'ri javoblar — hammasi QABUL qilinishi kerak
ACCEPTED = [
    # #F107 a1-10 «أَيْنَ ذَهَبْتَ؟»
    lat("qayerga bording", "qayerga ketding"),
    lat("qayerga bording", "qaerga bording"),
    lat("qayerga bording", "qayoqqa bording"),
    lat("qayerga bording", "Qayerga bordingiz?"),
    lat("qayerga bording", "sen qayerga bording"),
    lat("qayerga bording", "Қаерга бординг"),  # o'zbek kirilli
    lat("qayerga bording", "каерга бординг"),  # rus klaviaturasi
    # #F108 a2-11 «عَلَّمْتُ أَخِي» — so'z ichidagi «/»
    lat("men akamga/ukamga o'rgatdim", "men akamga o'rgatdim"),
    lat("men akamga/ukamga o'rgatdim", "ukamga o'rgatdim"),
    lat("men akamni/ukamni o'rgatdim", "men akamni o'rgatdim"),
    lat("men akamga/ukamga o'rgatdim", "men akamni o'qitdim", accept=["men akamni/ukamni o'qitdim"]),
    # #F110 a0-29 «كِتابٌ» — «bir» ixtiyoriy
    lat("bir kitob", "kitob"),
    lat("bir kitob", "китоб"),
    # #F111 a2-46 «سَاعِدْنِي!»
    lat("menga yordam bering", "yordam ber", accept=["yordam bering", "menga yordam ber", "yordam ber"]),
    # #F114 a2-22 «فِعْلٌ مُعْتَلٌّ»
    lat("illatli fe'l", "mu'tal fe'l", accept=["mu'tal fe'l"]),
    lat("illatli fe'l", "illatli fel"),
    lat("illatli fe'l", "иллатли феъл"),
    # #F116 a2-20 «أَنَا مَشْغُولٌ»
    lat("men bandman", "мен бандман"),
    lat("men bandman", "men bandmen"),
    lat("men bandman", "bandman"),
    # umumiy qoidalar
    lat("ilm — nur", "ilm nur"),
    lat("men Qur'on o'qidim", "Qur'onni o'qidim"),
    lat("kitob yangi", "kitob yangidir"),
    lat("isming nima", "ismingiz nima"),
    lat("sen kimsan", "siz kimsiz"),
    lat("u bormaydi", "u ketmaydi"),
    lat("u bordi", "u ketdi"),
    lat("ob-havo", "ob havo"),
    lat("bu opam/singlim", "bu mening singlim"),
    # #F112 a1-12, #F115 a2-22, #F117 a1-10 (arabchaga)
    ar("النَّاس", "ناس", mode="translate"),
    ar("النَّاس", "شعب", mode="translate", accept=["شَعْب"]),
    ar("قَالَ", "قالت", mode="translate", accept=["قَالَتْ"]),
    ar("أَمْس", "الامس", mode="translate"),
    ar("أَمْس", "البارحة", mode="translate", accept=["البَارِحَة"]),
    ar("سُؤَال", "سوال", mode="translate"),
    ar("كَتَبُوا", "كتبو", mode="translate"),
    ar("وُضُوء", "وضو", mode="translate"),
    ar("مَعْنَى", "معني", mode="translate"),
    ar("مَدْرَسَة", "مدرسه"),
]

# Ma'nosi boshqa javoblar — yumshoqlik ularni o'tkazib yubormasligi kerak
REJECTED = [
    lat("qayerga bording", "qayerga bordi"),  # shaxs
    lat("qayerga bording", "qayerda bording"),  # kelishik
    lat("men yozdim", "sen yozding"),
    lat("sen yozding", "siz yozdingiz lar"),
    lat("u bordi", "u keldi"),
    lat("men bandman", "sen bandsan"),
    lat("bir kitob", "ikki kitob"),
    lat("bir kitob", "qalam"),
    lat("sizlar yozdingiz", "sen yozding"),  # ko'plik o'rniga birlik — yo'q
    lat("men akamga/ukamga o'rgatdim", "men akamda o'rgatdim"),
    ar("كِتَاب", "قلم", mode="translate"),
    ar("النَّاس", "ناس"),  # diktant / to'ldirish — «ال» qat'iy
    ar("الْقَمَر", "قمر", mode="translate", prompt="'oy' so'zini aniqlik artikli bilan yozing."),
    ar("سُؤَال", "سوال"),  # diktantda hamza qat'iy
]


def test_reported_answers_now_accepted():
    res = run(ACCEPTED)
    bad = [(c[1], c[2]) for c, r in zip(ACCEPTED, res) if not r["ok"]]
    assert bad == []


def test_wrong_answers_still_rejected():
    res = run(REJECTED)
    bad = [(c[1], c[2]) for c, r in zip(REJECTED, res) if r["ok"]]
    assert bad == []


def test_notes_explain_leniency():
    r = run(
        [
            lat("bir kitob", "kitob"),
            ar("النَّاس", "ناس", mode="translate"),
            ar("مَعْنَى", "معني", mode="translate"),
            lat("men bandman", "men bandman"),
            lat("men bandman", "мен бандман"),
        ]
    )
    assert r[0]["ok"] and "bir" in r[0]["note"] and r[0]["exact"] is False
    assert "artikl" in r[1]["note"]
    assert "maqsura" in r[2]["note"]
    assert r[3] == {"ok": True, "exact": True}
    assert r[4]["ok"] and r[4]["exact"] is False  # kirillcha — lotin namunasi ko'rsatiladi


# /javoblar (30 kun, 1387 ta rad etilgan) — eng ko'p takrorlanganlari
REPORT_OK = [
    lat("sen (ayol) yozasan", "sen ayol yozasan"),  # qavs ichidagisi qavssiz
    lat("sen (ayol) yozding", "sen yozding ayol"),
    lat("ular ikkovi", "u ikkisi", accept=["ular ikkalasi", "ular ikkisi", "u ikkovi"]),
    lat("ular ikkovi", "Ular ikkisi"),
    lat("biz sovg'alarni yubordik", "biz hadya yubordik", accept=["biz hadya yubordik"]),
    lat("go'yo bola sherdek", "Bola xuddi sherdek", accept=["bola xuddi sherdek"]),
    ar("كَتَبُوا", "كتبو", mode="translate"),
    ar("كَتَبُوا", "هم كتبوا", mode="translate"),  # olmosh bilan
    ar("كَتَبُوا", "كتبو", mode="fill"),  # to'ldirishda ham jimjit alif kechiriladi
    ar("مَا زَالَ", "مازال", mode="translate"),
    ar("طَقْس", "الجو", mode="translate", accept=["جَوّ"]),
    ar("طَقْس", "الطقس", mode="translate"),
]
REPORT_WRONG = [  # (qat'iy qolishi kerak, izoh: qaysi joy xato)
    (ar("يَكْتُبَانِ", "تكتبان", mode="fill"), "Boshidagi harf"),
    (ar("تَكْتُبُونَ", "يكتبون", mode="translate"), "Boshidagi harf"),
    (ar("اِسْتَيْقَظْتُ", "استيقظ", mode="fill"), "tushib qolgan: «ـت»"),
    (ar("كَتَبُوا", "كتبا", mode="fill"), "«ـوا» kerak"),
    (ar("كَتَبُوا", "كتبنا", mode="translate"), "«ـوا» kerak"),
    (ar("يُعَلِّمُ", "علم", mode="fill"), "Boshidagi harf tushib qolgan: «يـ»"),
    (ar("كَتَبُوا", "كتبو"), None),  # diktant — qat'iy
    (lat("sen (ayol) yozasan", "u ayollar yozyadi"), None),
    (lat("go'yo bola sherdek", "Bola sher edi"), None),
    (lat("ular ishda hamkorlik qildilar", "ishchilar hamkorlik qildilar"), None),
]


def test_report_answers():
    res = run(REPORT_OK + [c for c, _ in REPORT_WRONG])
    ok, wrong = res[: len(REPORT_OK)], res[len(REPORT_OK) :]
    assert [(c[1], c[2]) for c, r in zip(REPORT_OK, ok) if not r["ok"]] == []
    for (case, hint), r in zip(REPORT_WRONG, wrong):
        assert not r["ok"], case
        if hint:
            assert hint in (r.get("note") or ""), (case, r)


def _content_item(lid: str, answer: str) -> dict:
    data = json.loads((ROOT / "content" / "modules" / lid.split("-")[0] / f"{lid}.json").read_text(encoding="utf-8"))
    (item,) = [t for t in data["micro_test"] if t.get("answer") == answer]
    return item


def _check_like_app(lid: str, answer: str, typed: list[str]) -> list[dict]:
    """exercises.tsx dagi kabi: tur bo'yicha mode, accept, to'ldirishda blankFills."""
    t = _content_item(lid, answer)
    accept = list(t.get("accept", []))
    if t["type"] == "fill_blank":
        import re

        m = re.search(r"«([^»]*_{2,}[^»]*)»", t.get("q_uz", ""))
        src = t.get("q_ar") or (m.group(1) if m else "")
        accept += run([["blankFills", src, t["answer"]]])[0]
    is_ar = any(0x0600 <= ord(ch) <= 0x06FF for ch in t["answer"])
    mode = {"translate_uz_ar": "translate", "fill_blank": "fill"}.get(t["type"], "strict")
    opts = {"accept": accept, "prompt": t.get("q_uz", ""), "mode": mode}
    return run([["arOk" if is_ar else "latOk", t["answer"], v, opts] for v in typed])


def test_report_week_answers():
    """/javoblar 7 kun (16–24): to'g'rilari endi o'tadi, xatolarga izoh."""
    ok_cases = {
        ("a2-32", "sog'liq puldan afzal"): ["salomlatlik puldan afzal", "Sog‘liq puldan muhimroq", "Sog‘liq mol-dunyodan afzalroq"],
        ("a2-05", "ular o'rganadilar"): ["o’rganadilar erkak"],
        ("a2-34", "uchinchi qavat"): ["Uchinshi qavat"],
        ("a2-15", "تَوَاصَلَ"): ["اتصل"],
        ("a0-01", "م"): ["ميم"],
        ("a2-08", "هُمْ"): ["علمهم"],
        ("a2-25", "بْنِي"): ["يبني", "بني"],
    }
    for (lid, ans), typed in ok_cases.items():
        res = _check_like_app(lid, ans, typed)
        assert all(r["ok"] for r in res), (lid, typed, res)

    wrong_cases = {
        ("a2-28", "مُجْتَهِدًا"): [("مجتحدا", "«ح» emas, «ه»"), ("مجتهد", "tushib qolgan: «ـا»")],
        ("b1-01", "نُشِرَ"): [("نشأ", None)],
        ("a2-13", "إِرْسَال"): [("أرسل", None)],
        ("a0-01", "م"): [("من", None)],
        ("a2-08", "هُمْ"): [("ارجال", None)],
    }
    for (lid, ans), cases in wrong_cases.items():
        res = _check_like_app(lid, ans, [v for v, _ in cases])
        for (v, hint), r in zip(cases, res):
            assert not r["ok"], (lid, v)
            if hint:
                assert hint in (r.get("note") or ""), (lid, v, r)


def _typed_items():
    for f in sorted((ROOT / "content" / "modules").glob("*/*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        for i, t in enumerate(data.get("micro_test", [])):
            if t.get("type") in ("translate_ar_uz", "translate_uz_ar", "fill_blank", "dictation") and not t.get("options"):
                yield f.stem, i, t


def test_content_answers_and_accepts_pass_own_check():
    """Har yozma savol: namuna aynan qabul, `accept` yozuvlari ham qabul (kontent xatosi bo'lmasin)."""
    cases, where = [], []
    for lid, i, t in _typed_items():
        is_ar = any(0x0600 <= ord(ch) <= 0x06FF for ch in t["answer"])
        fn = "arOk" if is_ar else "latOk"
        mode = {"translate_uz_ar": "translate", "fill_blank": "fill"}.get(t["type"], "strict")
        opts = {"accept": t.get("accept", []), "prompt": t.get("q_uz", ""), "mode": mode}
        cases.append([fn, t["answer"], t["answer"], opts])
        where.append((lid, i, t["answer"], "namuna"))
        for a in t.get("accept", []):
            cases.append([fn, t["answer"], a, opts])
            where.append((lid, i, a, "accept"))
    res = run(cases)
    bad = [w for w, r in zip(where, res) if not r["ok"] or (w[3] == "namuna" and not r.get("exact"))]
    assert bad == []
    assert len(cases) > 500


def test_reported_items_fixed_in_content():
    """#F108 va #F111 javoblari tuzatildi, qolganlariga muqobillar qo'shildi."""
    items = {(lid, t.get("q_ar") or t.get("q_uz")): t for lid, _i, t in _typed_items()}
    assert items[("a2-11", "عَلَّمْتُ أَخِي")]["answer"] == "men akamga/ukamga o'rgatdim"
    assert items[("a2-46", "سَاعِدْنِي!")]["answer"] == "menga yordam bering"
    assert "yordam bering" in items[("a2-46", "سَاعِدْنِي!")]["accept"]
    assert "mu'tal fe'l" in items[("a2-22", "فِعْلٌ مُعْتَلٌّ")]["accept"]
    assert "قَالَتْ" in items[("a2-22", "dedi")]["accept"]
    assert "men mashg'ulman" in items[("a2-20", "أَنَا مَشْغُولٌ")]["accept"]
    assert "شَعْب" in items[("a1-12", "odamlar, xalq")]["accept"]
    assert "البَارِحَة" in items[("a1-10", "kecha (kun)")]["accept"]
