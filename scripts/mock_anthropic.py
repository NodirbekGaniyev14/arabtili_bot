"""Anthropic API «muqallidi» — AI ustoz UI'sini kreditsiz sinash uchun.

Ishga tushirish: .claude/launch.json → "mock-ai" (port 9011), so'ng
data/preview/.env.preview fayliga:
    ANTHROPIC_BASE_URL=http://127.0.0.1:9011
    ANTHROPIC_API_KEY=mock
va "backend-preview"ni qayta ishga tushiring (scripts/preview_backend.py
shu faylni o'qiydi). Faqat POST /v1/messages — structured output (JSON
matn) shaklida oldindan yozilgan javoblar. Xabarlar soniga qarab tuzatish,
maslahat, yangi so'z va yakun (done) holatlari aylanib keladi.
"""

import json

import uvicorn
from fastapi import FastAPI, Request

app = FastAPI()

SCRIPT = [
    {
        "ar": "أَهْلًا وَسَهْلًا يَا صَدِيقِي! أَنَا جَمَال. مَا اسْمُكَ؟",
        "translit": "ahlan wa sahlan yaa sadiiqii! ana Jamaal. maa ismuka?",
        "uz": "Xush kelibsiz, do'stim! Men Jamolman. Isming nima?",
        "hint_uz": "Ismingizni ayting: اِسْمِي ...",
        "new_words": [{"ar": "اِسْم", "translit": "ism", "uz": "ism"}],
    },
    {
        "ar": "تَشَرَّفْنَا! مِنْ أَيْنَ أَنْتَ؟",
        "translit": "tasharrafnaa! min ayna anta?",
        "uz": "Tanishganimdan xursandman! Qayerdansiz?",
        "hint_uz": "Mamlakatingizni ayting: أَنَا مِنْ أُوزْبَكِسْتَان",
        "new_words": [],
        "correction": {"ok": False, "fixed_ar": "اِسْمِي نُودِير", "note_uz": "Arabchasi: ismii Nodir — «اسمي» + ism."},
    },
    {
        "ar": "أُوزْبَكِسْتَان بَلَدٌ جَمِيلٌ! مَاذَا تَعْمَلُ؟",
        "translit": "uzbakistaan baladun jamiil! maadhaa taʻmal?",
        "uz": "O'zbekiston go'zal mamlakat! Nima ish qilasiz?",
        "hint_uz": "",
        "new_words": [{"ar": "بَلَد", "translit": "balad", "uz": "mamlakat"}],
        "correction": {"ok": True, "fixed_ar": "", "note_uz": ""},
    },
    {
        "ar": "عَمَلٌ رَائِعٌ! هَلْ تُحِبُّ عَمَلَكَ؟",
        "translit": "ʻamalun raa'iʻ! hal tuhibbu ʻamalak?",
        "uz": "Ajoyib ish! Ishingizni yaxshi ko'rasizmi?",
        "hint_uz": "",
        "new_words": [],
        "correction": {"ok": False, "fixed_ar": "أَنَا طَالِبٌ", "note_uz": "Erkak uchun «طَالِب», «طَالِبَة» — ayol shakli."},
    },
]

FINAL = {
    "ar": "سَعِدْتُ بِالحَدِيثِ مَعَكَ! إِلَى اللِّقَاءِ.",
    "translit": "saʻidtu bil-hadiithi maʻak! ilal-liqaa'.",
    "uz": "Siz bilan suhbatlashganimdan xursandman! Ko'rishguncha.",
    "hint_uz": "",
    "new_words": [],
    "correction": {"ok": True, "fixed_ar": "", "note_uz": ""},
}


MOCK_QS = [
    ("مَا هِيَ مَسْؤُولِيَّاتُكَ فِي العَمَلِ؟", "maa hiya mas'uuliyyaatuka fil-ʻamal?", "Ishdagi mas'uliyatlaringiz nima?"),
    ("صِفْ يَوْمًا عَادِيًّا فِي عَمَلِكَ.", "sif yawman ʻaadiyyan fii ʻamalik.", "Ishdagi oddiy kuningizni tasvirlang."),
    ("مَاذَا تَفْعَلُ إِذَا غَضِبَ الزَّبُونُ؟", "maadhaa tafʻal idhaa gʻadiba az-zabuun?", "Mijoz g'azablansa nima qilasiz?"),
    ("مَا أَصْعَبُ شَيْءٍ فِي مِهْنَتِكَ؟", "maa asʻabu shay'in fii mihnatik?", "Kasbingizdagi eng qiyin narsa nima?"),
    ("لِمَاذَا اخْتَرْتَ هَذِهِ المِهْنَةَ؟", "limaadhaa ikhtarta haadhihil-mihna?", "Nega bu kasbni tanladingiz?"),
]


def _mock_reply(user_turns: int) -> dict:
    """SPEAKING MOCK EXAM rejimi: 5 savol, har javob baholanadi."""
    if user_turns == 0:
        q = MOCK_QS[0]
        return {"ar": "أَهْلًا! الاِمْتِحَانُ خَمْسَةُ أَسْئِلَةٍ. " + q[0], "translit": q[1], "uz": "Salom! Imtihon 5 savol. " + q[2],
                "score": -1, "vocab": -1, "grammar": -1, "content": -1,
                "feedback_uz": "", "ideal_ar": "", "done": False}
    done = user_turns >= 5
    q = MOCK_QS[min(user_turns, 4)]
    score = [72, 45, 88, 60, 95][min(user_turns - 1, 4)]
    return {
        "ar": "شُكْرًا! اِنْتَهَى الاِمْتِحَانُ." if done else q[0],
        "translit": "shukran! intahal-imtihaan." if done else q[1],
        "uz": "Rahmat! Imtihon tugadi." if done else q[2],
        "score": score,
        "vocab": min(100, score + 5),
        "grammar": max(0, score - 10),
        "content": score + 5 if score < 95 else 100,
        "feedback_uz": "Mavzuga mos, lekin fe'l shakli xato." if score < 80 else "Juda yaxshi, to'liq javob.",
        "ideal_ar": "أَنَا أَعْمَلُ فِي المُسْتَشْفَى وَأُسَاعِدُ المَرْضَى.",
        "done": done,
    }


@app.post("/v1/messages")
async def messages(req: Request):
    body = await req.json()
    msgs = body.get("messages", [])
    user_turns = sum(
        1 for m in msgs if m.get("role") == "user" and m.get("content") != "[START]"
    )
    sys_text = "".join(b.get("text", "") for b in body.get("system", []))
    if "SPEAKING MOCK EXAM" in sys_text:
        reply = _mock_reply(user_turns)
        return {
            "id": "msg_mock", "type": "message", "role": "assistant", "model": body.get("model", "mock"),
            "content": [{"type": "text", "text": json.dumps(reply, ensure_ascii=False)}],
            "stop_reason": "end_turn", "stop_sequence": None,
            "usage": {"input_tokens": 300, "output_tokens": 120, "cache_read_input_tokens": len(sys_text) // 3, "cache_creation_input_tokens": 0},
        }
    step = SCRIPT[min(user_turns, len(SCRIPT) - 1)] if user_turns < 6 else FINAL
    corr = step.get("correction", {"ok": True, "fixed_ar": "", "note_uz": ""})
    reply = {
        "ar": step["ar"],
        "translit": step["translit"],
        "uz": step["uz"],
        "correction_ok": corr["ok"] if user_turns else True,
        "fixed_ar": corr["fixed_ar"] if user_turns else "",
        "note_uz": corr["note_uz"] if user_turns else "",
        "hint_uz": step["hint_uz"],
        "new_words": step["new_words"],
        "answer_uz": (
            "«اِسْم» (ism) — «ism» degani. «اِسْمِي» = «mening ismim». Masalan: اِسْمِي نُودِير — ismii Nodir."
            if msgs and "?" in str(msgs[-1].get("content", "")) else ""
        ),
        "done": user_turns >= 6,
    }
    sys_len = sum(len(b.get("text", "")) for b in body.get("system", []))
    return {
        "id": "msg_mock",
        "type": "message",
        "role": "assistant",
        "model": body.get("model", "mock"),
        "content": [{"type": "text", "text": json.dumps(reply, ensure_ascii=False)}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {
            "input_tokens": 300,
            "output_tokens": 120,
            "cache_read_input_tokens": sys_len // 3,
            "cache_creation_input_tokens": 0,
        },
    }


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=9011)
