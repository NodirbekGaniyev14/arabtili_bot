"""Harakatli arabcha matn → o'zbekcha-lotin transliteratsiya (K17.5).

Talaffuz mashqi jumlalarida ishlatiladi: lug'at misollari to'liq harakatli,
lekin ularning transliti yo'q. Qoidalar lug'atdagi uslub bilan bir xil:
خ→x, غ→g', ث→th, ذ/ض/ظ→z, ع/ء→', و→v, cho'ziq unli ikkilanadi (aa/ii/uu),
qalin harflardan (ص ض ط ظ ق) keyin cho'ziq «aa» → «oo», shadda — undosh
ikkilanadi, artikl «al-»/«ash-» (quyosh harflari qo'shiladi), unlidan keyin
«l-» (vasl). Mukammal emas — ko'rsatma sifatida yetarli.
"""

import re

CONS = {
    "ب": "b", "ت": "t", "ث": "th", "ج": "j", "ح": "h", "خ": "x", "د": "d", "ذ": "z",
    "ر": "r", "ز": "z", "س": "s", "ش": "sh", "ص": "s", "ض": "z", "ط": "t", "ظ": "z",
    "ع": "'", "غ": "g'", "ف": "f", "ق": "q", "ك": "k", "ل": "l", "م": "m", "ن": "n",
    "ه": "h", "و": "v", "ي": "y", "ء": "'", "ؤ": "'", "ئ": "'",
    "گ": "g", "پ": "p", "چ": "ch", "ک": "k", "ی": "y", "ڤ": "v",
}
EMPHATIC = set("صضطظق")
SUN = set("تثدذرزسشصضطظلن")

FATHA, DAMMA, KASRA, SUKUN, SHADDA = "َ", "ُ", "ِ", "ْ", "ّ"
FATHATAN, DAMMATAN, KASRATAN, DAGGER, MADDA = "ً", "ٌ", "ٍ", "ٰ", "ٓ"
MARKS = {FATHA, DAMMA, KASRA, SUKUN, SHADDA, FATHATAN, DAMMATAN, KASRATAN, DAGGER, MADDA}
VOWEL_OF = {FATHA: "a", DAMMA: "u", KASRA: "i", FATHATAN: "an", DAMMATAN: "un", KASRATAN: "in"}

_ARABIC_WORD = re.compile(r"[؀-ۿ]+")
_PUNCT = {"،": ",", "؟": "?", "؛": ";", "ـ": ""}


def _units(word: str) -> list[tuple[str, set]]:
    """Harf + uning belgilari (harakat/shadda/sukun) ro'yxati."""
    out: list[tuple[str, set]] = []
    for ch in word:
        if ch in MARKS:
            if out:
                out[-1][1].add(ch)
        else:
            out.append((ch, set()))
    return out


def _bare(word: str) -> str:
    return "".join(ch for ch in word if ch not in MARKS)


def _long_a(prev_cons: str) -> str:
    return "oo" if prev_cons in EMPHATIC else "aa"


def _word(word: str, after_vowel: bool) -> str:
    units = _units(word)
    if not units:
        return ""
    bare = _bare(word)

    # «الله» / «لله» — o'zbekcha odat: Alloh (+ oxirgi harakat)
    if bare in ("الله", "ٱلله", "لله"):
        marks = units[-1][1]
        v = next((VOWEL_OF[m] for m in marks if m in VOWEL_OF), "")
        return ("lillaah" if bare == "لله" else "alloh") + v

    out: list[str] = []
    i = 0
    consumed_shadda = False

    # Artikl: ال / ٱل + (quyosh harfi bo'lsa qo'shiladi)
    if len(units) > 2 and units[0][0] in "اٱ" and units[1][0] == "ل" and units[1][1] <= {SUKUN, FATHA}:
        nxt = units[2][0]
        art_vowel = "" if after_vowel else "a"
        if nxt in SUN and SHADDA in units[2][1]:
            out.append(art_vowel + CONS.get(nxt, "") + "-")
            consumed_shadda = True
        else:
            out.append(art_vowel + "l-")
        i = 2

    prev_vowel = ""  # oxirgi chiqarilgan qisqa unli: a/u/i yoki ""
    prev_cons = ""
    n = len(units)
    word_start = i  # artikldan keyingi harf ham «bosh» hisoblanadi (al-arzu)

    while i < n:
        ch, marks = units[i]
        nxt_ch = units[i + 1][0] if i + 1 < n else ""
        nxt_marks = units[i + 1][1] if i + 1 < n else set()
        first = i == word_start
        last = i == n - 1
        vowel = next((VOWEL_OF[m] for m in marks if m in VOWEL_OF), "")
        has_sukun = SUKUN in marks

        # ── alif turlari ──
        if ch in "اٱ":
            if first:
                # Harakatsiz bosh alif (vasl): unlidan keyin jim («maa smuka»),
                # boshida «اسْتَ» → ista, aks holda «a»
                if not vowel and after_vowel:
                    i += 1
                    continue
                v = vowel or ("i" if (SUKUN in nxt_marks or SHADDA in nxt_marks) else "a")
                out.append(v)
                prev_vowel = v[0]
            elif prev_vowel == "a":
                # fatha + alif = cho'ziq (oldingi «a» ikkilanadi); tanvin bo'lsa jim
                if out and out[-1].endswith("an"):
                    pass
                else:
                    out[-1] = out[-1][:-1] + _long_a(prev_cons)
                    prev_vowel = "aa"
            elif vowel:
                out.append(vowel)
                prev_vowel = vowel[0]
            # aks holda (vasl/sukun'dan keyin) jim
            i += 1
            continue
        if ch == "آ":
            out.append(("" if first else "'") + "aa")
            prev_vowel, prev_cons = "aa", ""
            i += 1
            continue
        if ch == "ى":
            if FATHATAN in marks:
                out.append("an")
            elif prev_vowel == "a" and out:
                out[-1] = out[-1][:-1] + _long_a(prev_cons)
            else:
                out.append("aa")
            prev_vowel = "aa"
            i += 1
            continue
        if ch in "أإ":
            base = "" if first else "'"
            if ch == "إ":
                v = "i" if vowel in ("", "i") else vowel
            else:
                v = vowel or ("a" if first else "")
            out.append(base + v)
            prev_vowel = v[0] if v else ""
            prev_cons = ""
            i += 1
            continue

        # ── ta marbuta ──
        if ch == "ة":
            if vowel:
                out.append("t" + vowel)
                prev_vowel = vowel[0]
            elif prev_vowel == "aa":
                out.append("t")
                prev_vowel = ""
            else:
                out.append("a" if not (out and out[-1].endswith("a")) else "")
                prev_vowel = "a"
            i += 1
            continue

        # ── و / ي: cho'ziq unli, diftong yoki undosh ──
        if ch == "و" and not vowel and SHADDA not in marks and not first:
            if prev_vowel == "u":
                out.append("u")
                prev_vowel = "uu"
                i += 1
                continue
            if prev_vowel == "a" and (has_sukun or last or not (nxt_marks & set(VOWEL_OF)) and nxt_ch != "ا"):
                out.append("v")
                prev_vowel = ""
                i += 1
                continue
        if ch == "ي" and not vowel and SHADDA not in marks and not first:
            if prev_vowel == "i":
                out.append("i")
                prev_vowel = "ii"
                i += 1
                continue
            if prev_vowel == "a" and (has_sukun or last):
                out.append("y")
                prev_vowel = ""
                i += 1
                continue

        # ── oddiy undosh ──
        c = CONS.get(ch, ch)
        if SHADDA in marks and not consumed_shadda:
            c = c + c
        consumed_shadda = False
        # Oxirgi ِيّ → «iy» (arziyy → arziy)
        if ch == "ي" and SHADDA in marks and prev_vowel == "i" and not vowel and last:
            c = "y"
        # Cho'ziq unli: fatha + alif keyingi harfda (tanvin emas)
        if vowel == "a" and nxt_ch == "ا" and not (nxt_marks & set(VOWEL_OF)):
            out.append(c + _long_a(ch))
            prev_vowel, prev_cons = "aa", ch
            i += 2
            continue
        if DAGGER in marks:
            out.append(c + _long_a(ch))
            prev_vowel, prev_cons = "aa", ch
            i += 1
            continue
        out.append(c + vowel)
        prev_vowel = vowel[0] if vowel and vowel in ("a", "u", "i") else ""
        if vowel in ("an", "un", "in"):
            prev_vowel = ""
            # tanvin fathadan keyingi alif jim
            if vowel == "an" and nxt_ch in "اى":
                i += 1
        prev_cons = ch
        i += 1

    return "".join(out)


def translit(text: str) -> str:
    """Butun matn: arabcha so'zlar transliteratsiya, qolgani (raqam, tinish) qoladi."""
    for k, v in _PUNCT.items():
        text = text.replace(k, v)
    result: list[str] = []
    pos = 0
    prev_ends_vowel = False
    for m in _ARABIC_WORD.finditer(text):
        gap = text[pos : m.start()]
        result.append(gap)
        w = _word(m.group(), prev_ends_vowel and gap.strip() == "")
        result.append(w)
        prev_ends_vowel = bool(w) and w[-1] in "aiu"
        pos = m.end()
    result.append(text[pos:])
    return re.sub(r"[ \t]+", " ", "".join(result)).strip()
