"""K33 — services/answer_check.py (server) webapp/src/pages/v2/answerCheck.ts (mijoz) bilan BIR XIL hukm chiqarishi.

Mini-imtihon va chellenj ballini endi server hisoblaydi: yozma javob qoidalari ikki joyda yashaydi. Biri o'zgarib,
ikkinchisi qolsa — o'quvchi dars ichida «to'g'ri», imtihonda «xato» oladi. Bu test shuni ushlaydi:
  1. test_answer_check.py dagi qo'lda yozilgan hamma holatlar (hisobotlardan) — har ikki tekshiruvchida;
  2. butun kontent: har yozma savolning javobi, accept'lari va ularning buzilgan/o'zgargan ko'rinishlari.
"""

import glob
import json
import random
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
RUNNER = ROOT / "tests" / "js" / "answer_check_runner.cjs"
ESBUILD = ROOT / "webapp" / "node_modules" / "esbuild"

pytestmark = pytest.mark.skipif(
    not shutil.which("node") or not ESBUILD.exists(), reason="node yoki webapp/node_modules yo'q"
)


def _node(module: str, cases: list[list]) -> list[dict]:
    r = subprocess.run(
        ["node", str(RUNNER), module], input=json.dumps(cases), capture_output=True, text=True, encoding="utf-8"
    )
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _py(case: list) -> bool:
    from services import answer_check as ac

    fn, *args = case
    if fn == "latOk":
        answer, value, opts = args
        return ac.lat_ok(answer, value, accept=opts.get("accept"), prompt=opts.get("prompt", ""))
    if fn == "arOk":
        answer, value, opts = args
        return ac.ar_ok(answer, value, accept=opts.get("accept"), mode=opts.get("mode", "strict"), prompt=opts.get("prompt", ""))
    raise AssertionError(fn)


def test_curated_cases_agree(monkeypatch):
    """test_answer_check.py dagi har `run([...])` chaqiruvi: javoblar server tekshiruvchisida ham bir xil."""
    import test_answer_check as t

    seen: list[list] = []
    real = t.run

    def spy(cases):
        seen.extend(c for c in cases if c[0] in ("latOk", "arOk"))
        return real(cases)

    monkeypatch.setattr(t, "run", spy)
    for name in dir(t):
        fn = getattr(t, name)
        if name.startswith("test_") and callable(fn) and not fn.__code__.co_argcount:
            fn()
    assert len(seen) > 150, len(seen)
    ts = [r["ok"] for r in real(seen)]
    diff = [(c, p, x) for c, p, x in ((c, _py(c), x) for c, x in zip(seen, ts)) if p != x]
    assert not diff, diff[:5]


# ── Kontent korpusi ──


def _items() -> list[dict]:
    out = []
    for f in sorted(glob.glob(str(ROOT / "content/modules/*/*.json"))):
        out += json.load(open(f, encoding="utf-8")).get("micro_test", [])
    for f in sorted(glob.glob(str(ROOT / "content/exams/*_pool.json"))):
        d = json.load(open(f, encoding="utf-8"))
        out += [i for s in ("reading", "listening") for i in d[s]]
    return out


def _mutate(rnd: random.Random, s: str) -> str:
    if not s:
        return s
    arabic = any("؀" <= c <= "ۿ" for c in s)
    letters = "ابتثجحخدذرزسشصضطظعغفقكلمنهويةى" if arabic else "abcdefghiklmnoprstuvyz"
    k, i = rnd.randrange(8), rnd.randrange(len(s))
    if k == 0:
        return s[:i] + s[i + 1:]
    if k == 1:
        return s[:i] + rnd.choice(letters) + s[i:]
    if k == 2:
        return s[:i] + rnd.choice(letters) + s[i + 1:]
    if k == 3 and len(s) > 1:
        j = min(i, len(s) - 2)
        return s[:j] + s[j + 1] + s[j] + s[j + 2:]
    if k == 4:
        return " ".join(reversed(s.split(" ")))
    if k == 5:
        return s.upper()
    if k == 6:
        return s + rnd.choice([" bir", " ular", "ni", "dir", "lar", "ish", " ayol", " kishi", "ن", "ة", "ا", "ء"])
    return s.replace("o'", "u").replace("g'", "g").replace("q", "k").replace("h", "x")


def _cyr(s: str) -> str:
    s = s.lower()
    for k, v in {"sh": "ш", "ch": "ч", "yo": "ё", "yu": "ю", "ya": "я", "o'": "ў", "g'": "ғ"}.items():
        s = s.replace(k, v)
    tbl = dict(zip("abdefghijklmnopqrstuvxyz", "абдефгхижклмнопқрстувхйз"))
    return "".join(tbl.get(c, c) for c in s)


def _corpus() -> list[tuple[list, str]]:
    """[(case, node_module)] — hukmlar solishtiriladi."""
    from services import answer_check as ac

    rnd = random.Random(5)
    cases: list[tuple[list, str]] = []

    def lat(ans, v, acc, prompt):
        cases.append((["latOk", ans, v, {"accept": acc, "prompt": prompt}], "answerCheck.ts"))

    def ar(ans, v, acc, prompt, mode):
        cases.append((["arOk", ans, v, {"accept": acc, "prompt": prompt, "mode": mode}], "answerCheck.ts"))

    items = _items()
    for it in items:
        t, ans = it.get("type"), it.get("answer") or ""
        acc, prompt = it.get("accept") or [], it.get("q_uz", "")
        if not ans or (t in ("fill_blank", "harakat", "dictation", "translate_uz_ar") and len(it.get("options") or []) >= 2):
            continue
        if t == "translate_ar_uz" or (t == "fill_blank" and not ac.is_arabic(ans)):
            variants = {ans, ans.upper(), ans.replace("'", ""), _cyr(ans), ans.replace("sen", "siz"), "ular " + ans,
                        ans.replace("(", "").replace(")", ""), " ".join(reversed(ans.split(" "))), *acc}
            variants |= {_mutate(rnd, ans) for _ in range(5)} | {p.strip() for p in ans.split("/")}
            for v in variants:
                lat(ans, v, acc, prompt)
        elif t in ("translate_uz_ar", "fill_blank", "dictation"):
            bare = ac.norm_ar(ans)
            mode = {"translate_uz_ar": "translate", "fill_blank": "fill", "dictation": "strict"}[t]
            extra = ac.blank_fills(it.get("q_ar") or "", ans) if t == "fill_blank" else []
            variants = {ans, bare, bare.replace("ا", "أ"), bare.replace("ي", "ى"), bare.replace("ة", "ه"), bare.replace(" ", ""),
                        "ال" + bare, bare[2:] if bare.startswith("ال") else bare, "هم " + bare, ac.double_shadda(ans),
                        bare.replace("ؤ", "و").replace("ئ", "ي").replace("ء", ""), *acc, *extra}
            variants |= {_mutate(rnd, bare) for _ in range(5)}
            for v in variants:
                ar(ans, v, acc + extra, prompt if t != "dictation" else "", mode)
        elif t == "harakat" and not it.get("options"):
            for v in {ans, ac.norm_ar(ans), ans.replace("َ", ""), ans.replace("ْ", ""), ans + "ُ",
                      ans.replace("ُ", "َ"), ans.replace("ٌ", "")}:
                cases.append((["harakatCheck", v, ans], "exerciseLogic.ts"))

    # o'zaro: boshqa savolning javobi shu savolga (ortiqcha yumshoqlik)
    lat_items = [(i["answer"], i.get("accept") or [], i.get("q_uz", "")) for i in items if i.get("type") == "translate_ar_uz"]
    ar_items = [(i["answer"], i.get("accept") or [], i.get("q_uz", "")) for i in items if i.get("type") == "translate_uz_ar"]
    for _ in range(6000):
        a, acc, p = rnd.choice(lat_items)
        lat(a, rnd.choice(lat_items)[0], acc, p)
        a, acc, p = rnd.choice(ar_items)
        ar(a, rnd.choice(ar_items)[0], acc, p, "translate")
    return cases


def test_content_corpus_agrees():
    from services import answer_check as ac

    cases = _corpus()
    assert len(cases) > 12_000, len(cases)
    results: dict[int, bool] = {}
    for module in ("answerCheck.ts", "exerciseLogic.ts"):
        idx = [i for i, (_, m) in enumerate(cases) if m == module]
        for i, r in zip(idx, _node(module, [cases[i][0] for i in idx])):
            results[i] = r["ok"]
    diffs = []
    for i, (case, module) in enumerate(cases):
        py = ac.harakat_ok(case[2], case[1]) if module == "exerciseLogic.ts" else _py(case)
        if py != results[i]:
            diffs.append((case, f"py={py}", f"ts={results[i]}"))
    assert not diffs, (len(diffs), diffs[:5])
    assert 0.1 < sum(results.values()) / len(results) < 0.9, "korpus bir tomonlama emas"


def test_build_word_distractors_agree():
    """O'zak + vazn → chalg'ituvchi so'zlar mijozdagi bilan bir xil (variantlar tarkibi)."""
    from services import blind_quiz

    items = [i for i in _items() if i.get("type") == "build_word"]
    assert items
    payload = [["buildWordDistractors", {"root": i.get("root", ""), "answer": i["answer"]}] for i in items]
    ts = [r for r in _node("exerciseLogic.ts", payload)]
    for it, t in zip(items, ts):
        assert blind_quiz.build_word_distractors(it.get("root", ""), it["answer"]) == t, it
