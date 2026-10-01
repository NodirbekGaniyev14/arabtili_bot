"""Harf tinglash savollariga (ovozi yaqin harflar birga kelganda) `option_notes` qo'shadi (K29.5, #F160).

«Eshiting va harfni toping» — خَاء eshitilib, o'quvchi ح ni tanlasa: xato, lekin nega — ko'rsatilmasdi va u
«to'g'ri javobim xato hisoblandi» deb yozardi. Endi xato variant tagida ikkala harfning farqi chiqadi.
Fayl formati saqlanadi (matn darajasida tahrir). Qayta ishga tushirish xavfsiz (izohi bor savolga tegmaydi).

Ishlatish:  python scripts/add_letter_notes.py
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import audit_semantic as au  # noqa: E402

DESC = {
    "خ": "xā' — «x» kabi: tilning orqasidan, hirillab",
    "ح": "ḥā' — bo'g'izdan chiqadigan «h»: havo sekin, hirillashsiz",
    "ه": "hā' — oddiy yengil «h»",
    "ج": "jīm — «j»",
    "ت": "tā' — «t»",
    "س": "sīn — yupqa «s»",
    "ش": "shīn — «sh»",
    "ص": "ṣād — qalin «s» (og'iz to'la)",
    "ث": "thā' — tilni tish orasiga qo'yib «s» kabi",
    "ق": "qāf — bo'g'izga yaqin qalin «q»",
    "ك": "kāf — oddiy «k»",
    "غ": "ghayn — «g'» (g'arg'ara)",
    "ف": "fā' — «f»",
    "ع": "ʿayn — bo'g'iz torayishidan chiqadigan tovush",
    "ء": "hamza — bo'g'izdagi qisqa «to'xtash»",
    "ا": "alif — cho'ziq «ā»",
    "ض": "ḍād — qalin «d»",
    "د": "dāl — yupqa «d»",
    "ظ": "ẓā' — qalin «z»",
    "ذ": "dhāl — tilni tish orasiga qo'yib «z» kabi",
    "ز": "zāy — «z»",
    "و": "wāw — «w» yoki «u»",
}

BLOCK = re.compile(r"\{[^{}]*\}")


def notes_for(item: dict) -> dict[str, str] | None:
    atext = au.build_audio.collect().get(item.get("audio") or "", "")
    letter = au.LETTER_OF_NAME.get(atext)
    options = [str(o) for o in item.get("options") or []]
    answer = str(item.get("answer", "")).strip()
    if not letter or answer != letter or item.get("option_notes"):
        return None
    if not any(answer in grp and len([o for o in options if o in grp]) > 1 for grp in au.CONFUSABLE):
        return None
    heard = DESC.get(answer)
    if not heard:
        return None
    out = {}
    for o in options:
        if o != answer and o in DESC:
            out[o] = f"{DESC[o]}. Eshitilgan harf — «{answer}»: {heard}"
    return out or None


def main() -> int:
    changed = total = 0
    texts = au.audio_texts()
    au.build_audio.collect = lambda with_sources=False, _t=texts: _t  # bir marta hisoblaymiz
    files = sorted((ROOT / "content" / "modules").rglob("*.json")) + sorted((ROOT / "content" / "exams").glob("*_pool.json"))
    for f in files:
        raw = f.read_text(encoding="utf-8")
        raw = open(f, encoding="utf-8", newline="").read()
        count = 0

        def fix(m: re.Match) -> str:
            nonlocal count
            b = m.group(0)
            if '"audio"' not in b or '"options"' not in b:
                return b
            try:
                it = json.loads(b)
            except Exception:
                return b
            n = notes_for(it)
            if not n:
                return b
            count += 1
            add = ', "option_notes": ' + json.dumps(n, ensure_ascii=False)
            body = b[:-1].rstrip()
            tail = b[len(b[:-1].rstrip()):-1]  # yopuvchi qavsdan oldingi bo'shliq/yangi qator
            return body + add + tail + "}"

        out = BLOCK.sub(fix, raw)
        if count:
            json.loads(out)
            open(f, "w", encoding="utf-8", newline="").write(out)
            changed += 1
            total += count
            print(f"{f.relative_to(ROOT)}: {count} ta savol")
    print(f"JAMI: {total} ta savol, {changed} ta fayl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
