"""Yozma javob tekshiruvi — webapp/src/pages/v2/answerCheck.ts ning SERVER nusxasi (K33).

Mini-imtihon va haftalik chellenj ballini endi server hisoblaydi (mijozda to'g'ri javob yo'q), shuning uchun
yozma javob qoidalari (hamza, «ال», kirill, hurmat shakli, fe'l zamoni…) Python'da ham bo'lishi kerak.
Faqat HUKM (to'g'ri / xato) — imlo izohlari (arHint, note) mijozda qoladi: ular faqat ko'rsatish uchun.

DIQQAT: answerCheck.ts dagi qoida o'zgarsa — shu yerda ham o'zgartiring.
tests/test_answer_check_parity.py ikkalasini node orqali butun kontent + tasodifiy buzilgan javoblarda solishtiradi.
"""

from __future__ import annotations

import re

# ─────────────────────────── Arabcha ───────────────────────────

_HARAKAT = "ً-ْٰ"
_HARAKAT_RE = re.compile(f"[{_HARAKAT}]")
_SHADDA = "ّ"
_LETTER_MARKS = re.compile(f"([ء-ي])([{_HARAKAT}]*)")
STRICT_PROMPT = re.compile(r"artikl|\baniq|noaniq|tanvin|ال", re.I | re.A)


def is_arabic(s: str) -> bool:
    return bool(re.search("[؀-ۿ]", s or ""))


def norm_ar(s: str) -> str:
    s = _HARAKAT_RE.sub("", s)
    s = s.replace("ـ", "")  # tatvil
    s = re.sub("[أإآٱ]", "ا", s)  # أ إ آ ٱ → ا
    s = s.replace("ک", "ك").replace("ی", "ي")  # fors ک ی
    s = re.sub(r"[.,،؟!·:؛—–\s]+", " ", s)
    return s.strip()


def _ya_ta(s: str) -> str:
    return s.replace("ى", "ي").replace("ة", "ه")  # ى→ي ة→ه


def _hamza(s: str) -> str:
    return s.replace("ؤ", "و").replace("ئ", "ي").replace("ء", "")


def _waw_alif(s: str) -> str:
    return re.sub(r"وا(?=\s|\Z)", "و", s)


def _article(s: str) -> str:
    return " ".join(w[2:] if len(w) > 3 and w.startswith("ال") else w for w in s.split(" "))


_AR_PRONOUNS = {"انا", "نحن", "انت", "انتم", "انتن", "انتما", "هو", "هي", "هم", "هن", "هما"}


def _pronoun(s: str) -> str:
    w = s.split(" ")
    return " ".join(w[1:]) if len(w) > 1 and w[0] in _AR_PRONOUNS else s


def _spaces(s: str) -> str:
    return s.replace(" ", "")


def _apply_all(s: str, rules) -> str:
    for r in rules:
        s = r(s)
    return s


def double_shadda(s: str) -> str:
    """Ekran klaviaturasida shadda yo'q: «تعللم» = تَعَلُّم."""
    return _LETTER_MARKS.sub(lambda m: (m.group(1) * 2 if _SHADDA in m.group(2) else m.group(1)) + m.group(2), s)


_BLANK = re.compile(r"_{2,}")


def blank_fills(text: str, answer: str) -> list[str]:
    """To'ldirishda bo'sh joy so'zga yopishgan bo'lsa («عَلَّمَ___») — to'liq so'z va butun gap ham to'g'ri."""
    if not text or not _BLANK.search(text):
        return []
    out: list[str] = []
    word = next((w for w in re.split(r"\s+", text) if _BLANK.search(w)), "")
    if norm_ar(_BLANK.sub("", word, count=1)):
        out.append(_BLANK.sub(lambda _m: answer, word, count=1))
    out.append(_BLANK.sub(lambda _m: answer, text, count=1))
    return out


def ar_ok(answer: str, value: str, *, accept: list[str] | None = None, mode: str = "strict", prompt: str = "") -> bool:
    """mode: "strict" (diktant) | "fill" (+ «ـوا» alifi) | "translate" (+ hamza, «ال», olmosh, bo'shliq)."""
    v = norm_ar(value or "")
    if not v:
        return False
    accept = list(accept or [])
    main = norm_ar(answer)
    if v == main:
        return True
    alts = [a for a in (norm_ar(x) for x in accept) if a]
    if v in alts:
        return True

    rules = [_ya_ta]
    if mode != "strict":
        rules.append(_waw_alif)
    if mode == "translate":
        rules.append(_hamza)
        if not STRICT_PROMPT.search(prompt or ""):
            rules.append(_article)
        rules += [_pronoun, _spaces]
    folded = _apply_all(v, rules)
    for target in [main, *alts]:
        if _apply_all(target, rules) == folded:
            return True
    # Qo'sh undosh ikki harf bilan yozilgan («تعللم») — to'g'ri
    for raw in [answer, *accept]:
        dbl = norm_ar(double_shadda(raw))
        if dbl != norm_ar(raw) and _apply_all(dbl, rules) == folded:
            return True
    return False


# ── Harakat qo'yish (exerciseLogic.ts harakatVerdict) ──

_OPTIONAL_MARKS = "ْٰ"  # sukun va xanjar alif — yo'qligi xato emas
_CASE_ENDING = re.compile("^[ً-ِ]$")


def split_harakat(word: str) -> list[list[str]]:
    """[[harf, harakatlar], …] — harakat belgisi oldingi harfga yopishadi."""
    out: list[list[str]] = []
    for ch in word.replace("ـ", ""):
        if _HARAKAT_RE.match(ch) and out:
            out[-1][1] += ch
        else:
            out.append([ch, ""])
    return out


def _mark_key(marks: str, strict: bool) -> str:
    if not strict:
        marks = "".join(c for c in marks if c not in _OPTIONAL_MARKS)
    return "".join(sorted(marks))


def harakat_ok(answer: str, given: str) -> bool:
    ans = split_harakat(answer)
    user = split_harakat(given or "")
    if len(user) != len(ans) or any(u[0] != a[0] for u, a in zip(user, ans)):
        return False
    strict = [i for i, (u, a) in enumerate(zip(user, ans)) if _mark_key(u[1], True) != _mark_key(a[1], True)]
    loose = [i for i, (u, a) in enumerate(zip(user, ans)) if _mark_key(u[1], False) != _mark_key(a[1], False)]
    if not strict or not loose:
        return True
    last = len(ans) - 1
    while last > 0 and not re.search("[؀-ۿ]", ans[last][0]):
        last -= 1
    user_end = "".join(c for c in user[last][1] if c not in _OPTIONAL_MARKS)
    ans_end = "".join(c for c in ans[last][1] if c not in _OPTIONAL_MARKS)
    if len(loose) == 1 and loose[0] == last:
        if not user_end and ans_end:
            return True  # E'rob: oxirgi harakat qo'yilmagan
        if not ans_end and _CASE_ENDING.match(user_end):
            return True  # namunada yalang'och, o'quvchi e'rob harakati qo'ygan
    return False


# ─────────────────────────── O'zbekcha (lotin) ───────────────────────────

_APOS = "'ʼ’‘ʻ`´"
_NUMS = ["", "bir", "ikki", "uch", "to'rt", "besh", "olti", "yetti", "sakkiz", "to'qqiz", "o'n"]
_ORD = ["", "birinchi", "ikkinchi", "uchinchi", "to'rtinchi", "beshinchi", "oltinchi", "yettinchi", "sakkizinchi",
        "to'qqizinchi", "o'ninchi"]
# JS `\b` / `\d` — faqat ASCII; Python'da shuni lookaround bilan qaytaramiz
_ORD_RE = re.compile(r"(?<![A-Za-z0-9_])([0-9]{1,2})\s*-\s*(?=[a-z])")
_NUM_RE = re.compile(r"(?<![A-Za-z0-9_])([0-9]{1,2})(?![A-Za-z0-9_])")
_DROP_RE = re.compile("[" + re.escape(_APOS) + r"\-_.?!:;«»\"“”—–…]")


def norm_lat(s: str) -> str:
    s = s.lower()

    def ordinal(m):
        n = int(m.group(1))
        return _ORD[n] + " " if n < len(_ORD) and _ORD[n] else m.group(0)

    def number(m):
        n = int(m.group(1))
        return _NUMS[n] if n < len(_NUMS) and _NUMS[n] else m.group(0)

    s = _ORD_RE.sub(ordinal, s)
    s = _NUM_RE.sub(number, s)
    s = _DROP_RE.sub("", s)
    return re.sub(r"\s+", " ", s).strip()


_CYR = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "ё": "yo", "ж": "j", "з": "z", "и": "i", "й": "y", "к": "k",
    "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "x",
    "ц": "s", "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "'", "ы": "i", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "ў": "o'", "қ": "q", "ғ": "g'", "ҳ": "h",
}
_CYR_LETTER = re.compile("[а-яёўқғҳ]")
_CYR_SOFT = re.compile("[аеёиоуўэюяъь]")


def has_cyr(s: str) -> bool:
    return bool(re.search("[Ѐ-ӿ]", s))


def cyr_to_lat(s: str) -> str:
    low = s.lower()
    out = []
    for i, ch in enumerate(low):
        if ch == "е":
            prev = low[i - 1] if i else ""
            out.append("ye" if not prev or not _CYR_LETTER.match(prev) or _CYR_SOFT.match(prev) else "e")
        else:
            out.append(_CYR.get(ch, ch))
    return "".join(out)


def _ru_fold(s: str) -> str:
    s = s.lower()
    s = re.sub("o[" + re.escape(_APOS) + "]", "u", s)
    s = re.sub("g[" + re.escape(_APOS) + "]", "g", s)
    return s.replace("q", "k").replace("h", "x")


_WHOLE_SPLIT = re.compile(r"\s+/\s*|\s*/\s+|\s*[,;]\s*|\s+yoki\s+")
_TYPED_SPLIT = re.compile(r"\s+/\s*|\s*/\s+|\s+yoki\s+")


def _expand_slashes(s: str) -> list[str]:
    acc = [""]
    for w in (x for x in re.split(r"\s+", s) if x):
        alts = [x for x in w.split("/") if x]
        acc = [(f"{a} {x}" if a else x) for a in acc for x in alts][:24]
    return acc


def _lat_variants(answer: str) -> list[str]:
    out: list[str] = []

    def push(s: str):
        for part in _WHOLE_SPLIT.split(s):
            for e in _expand_slashes(part):
                n = norm_lat(e)
                if n:
                    out.append(n)

    tail = re.search(r"\(([^)]*)\)\s*\Z", answer)
    if tail:
        push(tail.group(1))
    push(re.sub(r"\([^)]*\)", " ", answer))
    push(re.sub(r"[()]", " ", answer))
    push(answer)
    return list(dict.fromkeys(out))


_PRONOUNS = {"men", "sen", "u", "biz", "siz", "ular", "sizlar", "mening", "sening", "uning", "bizning", "sizning",
             "ularning"}
_SYNONYMS = {
    "muannas": "ayol", "muzakkar": "erkak", "hamda": "va",
    "qaerga": "qayerga", "qaerda": "qayerda", "qaerdan": "qayerdan", "qayoqqa": "qayerga", "qayoqda": "qayerda",
    "qayda": "qayerda", "man": "men", "ila": "bilan",
    "kondisioner": "konditsioner", "kondicioner": "konditsioner", "kondisaner": "konditsioner",
    "konditsaner": "konditsioner", "kandisioner": "konditsioner", "kandisaner": "konditsioner",
}


def _norm_ikki(w: str) -> str:
    m = re.fullmatch(r"ikk(ov|ala|i)(.*)", w)
    if not m:
        return w
    if m.group(1) == "ov":
        rest = m.group(2)
    else:
        rest = re.sub(r"^m", "im", re.sub(r"^ng", "ing", re.sub(r"^s?i", "i", m.group(2), count=1), count=1), count=1)
    return "ikkov" + rest


_STEM_ALT = {"bor": ["ket"], "de": ["ayt"], "ayt": ["de"], "yubor": ["jonat", "yolla"], "jonat": ["yubor", "yolla"]}
_POLITE = {"sen": "siz", "ng": "ngiz", "san": "siz", "sizlar": "siz"}
_PRES = {"di": "ti", "dilar": "tilar"}
_PAST = {"man": "m", "san": "ng", "miz": "k", "siz": "ngiz"}


def _verb_canon(w: str) -> str:
    m = re.fullmatch(r"(.{2,}?)(?:yap|yab|mo[qk]da)(man|san|ti|di|miz|siz|tilar|dilar)?", w)
    if m:
        g2 = m.group(2)
        return f"{m.group(1)}|hoz|{_PRES.get(g2, g2) if g2 else 'ti'}"
    m = re.fullmatch(r"(.{2,}?)ma(di|dim|ding|dik|dingiz|dilar)", w)
    if m:
        return f"{m.group(1)}|otgma|{m.group(2)[2:]}"
    m = re.fullmatch(r"(.{2,}?)[ay](man|san|di|miz|siz|dilar)", w)
    if m:
        return f"{m.group(1)}|hoz|{_PRES.get(m.group(2), m.group(2))}"
    m = re.fullmatch(r"(.{2,}?)di(m|ng|k|ngiz|lar)?", w)
    if m:
        return f"{m.group(1)}|otg|{m.group(2) or ''}"
    m = re.fullmatch(r"(.{2,}?)(?:gan|kan|qan)(man|san|miz|siz|lar)?", w)
    if m:
        g2 = m.group(2)
        return f"{m.group(1)}|otg|{_PAST.get(g2, g2) if g2 else ''}"
    return w


_NOTE_WORDS = {"jins", "koplikda", "birlikda"}
_GENDER = {"ayol", "erkak"}


def _canon_tokens(s: str) -> list[str]:
    words = [w for w in re.split(r"\s+", re.sub(r"\([^)]*\)", " ", s)) if w and w not in _NOTE_WORDS]
    words = [_norm_ikki(_SYNONYMS.get(w, w)) for w in words]
    words = [w for i, w in enumerate(words) if not (w == "kishi" and i > 0 and words[i - 1] in _GENDER)]
    t = [_verb_canon(w.replace("x", "h")) for w in words]
    if "ular" in t:
        t = [w + "lar" if w.endswith("|otg|") or w.endswith("|hoz|ti") else w for w in t]
    return t


def _typo_close(x: str, y: str) -> bool:
    if len(x) == len(y):
        i = 0
        while i < len(x) and x[i] == y[i]:
            i += 1
        return i < len(x) - 1 and x[i] == y[i + 1] and x[i + 1] == y[i] and x[i + 2:] == y[i + 2:]
    if abs(len(x) - len(y)) != 1:
        return False
    long, short = (x, y) if len(x) > len(y) else (y, x)
    i = 0
    while i < len(short) and long[i] == short[i]:
        i += 1
    return long[i + 1:] == short[i:] and (
        (i + 1 < len(long) and long[i] == long[i + 1]) or (i > 0 and long[i] == long[i - 1])
    )


def _lev1(a: str, b: str) -> bool:
    if abs(len(a) - len(b)) > 1:
        return False
    i = 0
    while i < len(a) and i < len(b) and a[i] == b[i]:
        i += 1
    if len(a) == len(b):
        return a[i + 1:] == b[i + 1:]
    long, short = (a, b) if len(a) > len(b) else (b, a)
    return long[i + 1:] == short[i:]


def _stem_ok(e: str, g: str) -> bool:
    if e == g:
        return True
    neg = e.endswith("ma") and g.endswith("ma")
    e0, g0 = (e[:-2], g[:-2]) if neg else (e, g)
    return g0 in _STEM_ALT.get(e0, []) or (len(e0) >= 4 and _typo_close(e0, g0))


def _ish_plural(es: str, gs: str, ep: str) -> bool:
    return ep in ("tilar", "lar") and (gs == es + "ish" or (bool(re.search("[aeiou]$", es)) and gs == es + "sh"))


def _verb_close(e: str, g: str) -> bool:
    es, et, ep = (e.split("|") + ["", "", ""])[:3]
    gs, gt, gp = (g.split("|") + ["", "", ""])[:3]
    return et == gt and (_stem_ok(es, gs) or _ish_plural(es, gs, ep)) and (ep == gp or _POLITE.get(ep) == gp)


_CASES = ["ning", "dan", "ga", "ka", "qa", "da", "ta", "ni"]


def _case_swap(e: str, g: str) -> bool:
    def split(w: str):
        c = next((x for x in _CASES if w.endswith(x) and len(w) > len(x) + 1), None)
        return (w[: -len(c)], c) if c else (w, "")

    es, ec = split(e)
    gs, gc = split(g)
    return es == gs and ec != gc


def _word_close(e: str, g: str) -> bool:
    if e == g:
        return True
    ev, gv = "|" in e, "|" in g
    if ev or gv:
        return ev and gv and _verb_close(e, g)
    if _POLITE.get(e) == g:
        return True
    if e.endswith("ng") and g == e + "iz":
        return True
    if e.endswith("san") and g == e[:-3] + "siz":
        return True
    if g == e + "ni" or e == g + "ni":
        return True
    if g == e + "dir" or e == g + "dir":
        return True
    if e.endswith("ning") and g == e[:-4] + "ni":
        return True
    if len(e) >= 3 and e in _PRONOUNS and g not in _PRONOUNS and len(g) == len(e) and _lev1(e, g):
        return True
    if _case_swap(e, g):
        return False
    if max(len(e), len(g)) >= 7 and min(len(e), len(g)) >= 5 and _lev1(e, g):
        return True
    return len(e) >= 4 and _typo_close(e, g)


_SOFT_SUBS = {"ei", "ie", "bp", "pb", "gh", "hg", "kq", "qk"}


def _soft_typo(e: str, g: str) -> bool:
    if e == g or len(e) != len(g) or len(e) < 5:
        return False
    diff = [i for i, ch in enumerate(e) if ch != g[i]]
    return len(diff) == 1 and (e[diff[0]] + g[diff[0]]) in _SOFT_SUBS


def _vowel_drop(e: str, g: str) -> bool:
    if len(e) < 5 or len(g) != len(e) - 1 or _verb_canon(g) != g:
        return False
    return any(e[k] in "aeiou" and e[:k] + e[k + 1:] == g for k in range(1, len(e) - 1))


def _seq_close(a: list[str], b: list[str]) -> bool:
    return len(a) == len(b) and all(_word_close(w, b[i]) for i, w in enumerate(a))


def _tokens_match(a: list[str], b: list[str]) -> bool:
    def close(x, y):
        return _seq_close(x, y) or _seq_close(sorted(x), sorted(y))

    if close(a, b):
        return True
    pa = any(w in _PRONOUNS for w in a)
    pb = any(w in _PRONOUNS for w in b)
    if pa == pb:
        return False
    sa = [w for w in a if w not in _PRONOUNS]
    sb = [w for w in b if w not in _PRONOUNS]
    return bool(sa) and bool(sb) and close(sa, sb)


def _lat_match(answer: str, typed: str, accept: list[str], prompt: str) -> bool:
    raw = norm_lat(typed)
    if not raw:
        return False
    if raw == norm_lat(answer):
        return True
    if any(norm_lat(a) == raw for a in accept):
        return True
    parts = [e for p in _TYPED_SPLIT.split(typed) for e in _expand_slashes(p)]
    if len(parts) > 1:
        return all(_lat_match(answer, p, accept, prompt) for p in parts)
    nv = re.sub(r"\s+", " ", re.sub(r"[,;]", " ", raw)).strip()
    main = _lat_variants(answer)
    if nv in main:
        return True
    extra = [v for a in accept for v in _lat_variants(a)]
    if nv in extra:
        return True

    all_v = [*main, *extra]
    vt = _canon_tokens(nv)
    if vt and any(_tokens_match(_canon_tokens(v), vt) for v in all_v):
        return True
    squash = nv.replace(" ", "")
    if any(v.replace(" ", "") == squash for v in all_v):
        return True

    for v in all_v:
        words = v.split(" ")
        fixed = " ".join(next((w for w in words if _soft_typo(w, g) or _vowel_drop(w, g)), g) for g in nv.split(" "))
        if fixed != nv and _tokens_match(_canon_tokens(v), _canon_tokens(fixed)):
            return True

    if not STRICT_PROMPT.search(prompt or ""):
        def no_bir(t: list[str]) -> list[str]:
            return [w for w in t if w != "bir"]

        for v in all_v:
            at = _canon_tokens(v)
            with_bir = "bir" in at
            if with_bir != ("bir" in vt) and no_bir(vt) and _tokens_match(no_bir(at), no_bir(vt)):
                return True
    return False


def lat_ok(answer: str, value: str, *, accept: list[str] | None = None, prompt: str = "") -> bool:
    accept = list(accept or [])
    value = value or ""
    if not has_cyr(value):
        return _lat_match(answer, value, accept, prompt)
    typed = cyr_to_lat(value)
    if _lat_match(answer, typed, accept, prompt):
        return True
    return _lat_match(_ru_fold(answer), _ru_fold(typed), [_ru_fold(a) for a in accept], prompt)
