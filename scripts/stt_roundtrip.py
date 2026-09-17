"""TTS → STT aylanma sinovi: ustoz/mashq jumlalari edge-tts bilan o'qiladi, Whisper
bilan qayta yoziladi va `pronunciation_score` bilan solishtiriladi.

Nima uchun: «ma'lum tovushlar tanilmayapti / xato o'qilmoqda» shikoyatini
o'lchash — qaysi jumlalar/harflar TTS'da noto'g'ri o'qiladi yoki STT'da boshqacha
yoziladi (hamza, ta-marbuta, raqamlar, bo'sh joy...). Natija: eng yomon jumlalar
va so'z-so'z nomuvofiqlik namunalari — normalize/scorer'ni shunga qarab tuzatamiz.

Ishlatish (STT_API_KEY .env'da bo'lishi kerak; Groq narxi ~$0.04/soat audio):
    .venv/Scripts/python scripts/stt_roundtrip.py            # ~200 jumla
    .venv/Scripts/python scripts/stt_roundtrip.py --limit 40
    .venv/Scripts/python scripts/stt_roundtrip.py --target   # Whisper'ga maqsad matn prompt bo'lib beriladi
Natija: data/preview/roundtrip.json (to'liq) + konsolda xulosa.
"""

import argparse
import asyncio
import json
import os
import random
import sys
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("DB_PATH", str(ROOT / "data" / "preview" / "arabiy.db"))

from services import daily, drill, stt, tts, tutor  # noqa: E402
from services.reference import normalize  # noqa: E402


def collect(limit: int) -> list[dict]:
    items: list[dict] = []
    for level, qs in daily.bank().items():
        for q in qs:
            items.append({"src": f"daily:{q['id']}", "level": level, "ar": q["ar"]})
    rng = random.Random(7)
    for t in tutor.TOPICS:
        if not t["themes"]:
            continue
        for level in ("A1", "B1"):
            for s in drill.sentences(level, t["id"], 6, random.Random(rng.random())):
                items.append({"src": f"drill:{t['id']}:{level}", "level": level, "ar": s["ar"]})
    seen: set[str] = set()
    out = []
    for it in items:
        k = normalize(it["ar"])
        if k in seen:
            continue
        seen.add(k)
        out.append(it)
    return out[:limit]


def nearest(word: str, heard_words: list[str]) -> tuple[str, float]:
    best, ratio = "", 0.0
    for h in heard_words:
        r = SequenceMatcher(None, word, h).ratio()
        if r > ratio:
            best, ratio = h, r
    return best, ratio


STT_PACE = 3.1  # s — Groq bepul tarifi 20 so'rov/daqiqa


async def run(items: list[dict], with_target: bool) -> list[dict]:
    # 1) TTS — parallel (edge-tts), diskda cache'lanadi
    sem = asyncio.Semaphore(3)

    async def synth(it: dict) -> str:
        async with sem:
            key = await tts.synthesize(it["ar"], it["level"])
            if not key:  # vaqtinchalik xato — bir marta qayta
                key = await tts.synthesize(it["ar"], it["level"])
            return key

    keys = await asyncio.gather(*(synth(it) for it in items))
    # 2) STT — ketma-ket, sur'at cheklangan (429 bo'lsa stt o'zi bir marta kutib qaytaradi)
    results = []
    for n, (it, key) in enumerate(zip(items, keys), 1):
        if not key:
            results.append({**it, "error": "tts"})
            continue
        audio = tts.path_for(key).read_bytes()
        heard, conf = await stt.transcribe_ex(
            audio, f"{key}.mp3", "audio/mpeg", prompt=it["ar"] if with_target else ""
        )
        if not heard:
            results.append({**it, "error": f"stt:{stt.last_error or 'empty'}"})
        else:
            sc = tutor.pronunciation_score(it["ar"], heard)
            results.append({**it, "heard": heard, "conf": conf, "score": sc["score"], "words": sc["words"]})
        if n % 20 == 0:
            print(f"  {n}/{len(items)}…", flush=True)
        await asyncio.sleep(STT_PACE)
    return results


def report(results: list[dict]) -> None:
    ok = [r for r in results if "score" in r]
    errs = [r for r in results if "error" in r]
    print(f"\nJami {len(results)} jumla · baholangan {len(ok)} · xato {len(errs)}")
    if errs:
        print("  xatolar:", Counter(r["error"] for r in errs).most_common())
    if not ok:
        return
    scores = [r["score"] for r in ok]
    print(f"O'rtacha ball: {sum(scores) / len(scores):.1f} · ≥90: {sum(s >= 90 for s in scores)} · "
          f"80–89: {sum(80 <= s < 90 for s in scores)} · 60–79: {sum(60 <= s < 80 for s in scores)} · <60: {sum(s < 60 for s in scores)}")
    confs = [r["conf"] for r in ok if r.get("conf", -1) >= 0]
    if confs:
        print(f"Whisper aniqlik (conf) o'rtacha: {sum(confs) / len(confs):.0f}")

    # So'z darajasida nomuvofiqlik: maqsad so'z ↔ eng yaqin eshitilgan so'z
    pairs: Counter = Counter()
    missing_words = 0
    total_words = 0
    for r in ok:
        heard_words = [w for w in tutor._clean(r["heard"]).split() if w]
        for w in r["words"]:
            total_words += 1
            if w["ok"]:
                continue
            missing_words += 1
            tw = tutor._clean(w["ar"])
            near, ratio = nearest(tw, heard_words)
            pairs[(tw, (near if ratio >= 0.5 else "∅") + (" (yaqin)" if w.get("close") else ""))] += 1
    print(f"So'zlar: {total_words} · topilmadi: {missing_words} ({missing_words * 100 / max(total_words, 1):.1f}%)")
    print("\nEng ko'p uchraydigan so'z nomuvofiqliklari (maqsad → eshitildi):")
    for (a, b), n in pairs.most_common(40):
        print(f"  {n:3d}  {a}  →  {b}")

    print("\nEng yomon 30 jumla:")
    for r in sorted(ok, key=lambda r: r["score"])[:30]:
        miss = " ".join(w["ar"] for w in r["words"] if not w["ok"])
        print(f"  [{r['score']:3d}] {r['src']}\n        maqsad: {r['ar']}\n        eshit.: {r['heard']}\n        yo'q:   {miss}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=220)
    ap.add_argument("--target", action="store_true", help="Whisper prompt = maqsad jumla")
    ap.add_argument("--out", default=str(ROOT / "data" / "preview" / "roundtrip.json"))
    args = ap.parse_args()
    if not stt.available():
        print("STT_API_KEY yo'q (.env) — Whisper'siz aylanma sinov bo'lmaydi.")
        sys.exit(2)
    items = collect(args.limit)
    print(f"{len(items)} jumla: TTS → Whisper ({'maqsad prompt' if args.target else 'neytral prompt'})…")
    results = asyncio.run(run(items, args.target))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    report(results)
    print(f"\nTo'liq natija: {args.out}")


if __name__ == "__main__":
    main()
