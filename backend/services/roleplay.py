"""AI rol o'yini — Saudiya vaziyatlarida matnli dialog simulyatsiyasi (K7).

Kredit bo'lsa: Claude rolni jonli o'ynaydi (hijoziy lahja, A2 daraja).
Kredit yo'q bo'lsa: oldindan yozilgan «skript» bo'yicha yuradi (offline ham ishlaydi).
"""

from config import settings

# Har vaziyat: kim (rol), ochilish, AI tizim prompti, va zaxira skript.
SCENARIOS: dict[str, dict] = {
    "taxi": {
        "title_uz": "Taksi haydovchisi",
        "emoji": "🚕",
        "desc_uz": "Jiddadan Makkaga taksida — narxni kelishing.",
        "system": (
            "Sen Jiddadagi mehmondo'st taksi haydovchisisan. O'quvchi (A2 darajali "
            "arab tili o'rganuvchi) mijoz. HIJOZIY lahjada, SODDA va QISQA gaplar bilan "
            "javob ber (1-2 jumla). Mijozni Makkaga olib borasan, narxni kelishasan. "
            "Tabiiy va samimiy bo'l. Har javobingni ARABCHA yoz."
        ),
        "script": [
            {"ar": "أَهْلًا وَسَهْلًا! وِين تَبْغَى تَرُوح؟", "uz": "Xush kelibsiz! Qayerga bormoqchisiz?"},
            {"ar": "تَمَام، مَكَّة. التَّوْصِيلَة بِمِئَة رِيَال.", "uz": "Yaxshi, Makka. Yo'l 100 riyol."},
            {"ar": "طَيِّب طَيِّب، تِسْعِين رِيَال. يَلّا نَرُوح!", "uz": "Mayli, 90 riyol. Qani ketdik!"},
            {"ar": "وَصَلْنَا لِلْحَرَم. اللَّه يَحْفَظُك، عُمْرَة مَقْبُولَة!", "uz": "Haramga yetib keldik. Xudo asrasin, umrangiz qabul bo'lsin!"},
        ],
    },
    "restaurant": {
        "title_uz": "Restoran ofitsianti",
        "emoji": "🍽️",
        "desc_uz": "Restoranda ovqat buyurtma qiling — halolligini so'rang.",
        "system": (
            "Sen Makkadagi restoran ofitsiantisan. O'quvchi (A2) mijoz. HIJOZIY lahjada, "
            "SODDA va QISQA javob ber. Menyu taklif qilasan, buyurtma olasan, halol "
            "haqida savolga javob berasan, hisobni keltirasan. Har javobing ARABCHA."
        ),
        "script": [
            {"ar": "حَيَّاك اللَّه! تَفَضَّل، وِش تَبْغَى تَطْلُب؟", "uz": "Xush kelibsiz! Marhamat, nima buyurtma qilasiz?"},
            {"ar": "أَكِيد حَلَال، كُلّ شَيْء عِنْدِنَا حَلَال. الكَبْسَة زَيْنَة وَاجِد!", "uz": "Albatta halol, hammasi halol. Kabsa juda zo'r!"},
            {"ar": "تَمَام، كَبْسَة دَجَاج وَعَصِير. لَحْظَة لَو سَمَحْت.", "uz": "Yaxshi, tovuqli kabsa va sharbat. Bir lahza, iltimos."},
            {"ar": "تَفَضَّل، هَذِي الفَاتُورَة. صَحَّتَيْن وَعَافِيَة!", "uz": "Marhamat, mana hisob. Yoqimli ishtaha!"},
        ],
    },
    "hotel": {
        "title_uz": "Mehmonxona xodimi",
        "emoji": "🏨",
        "desc_uz": "Mehmonxonaga check-in qiling — muammoni hal qiling.",
        "system": (
            "Sen Makkadagi mehmonxona qabulxona (reception) xodimisan. O'quvchi (A2) "
            "mehmon. HIJOZIY lahjada SODDA javob ber. Bron, kalit, xona muammosi bilan "
            "yordam berasan. Har javobing ARABCHA."
        ),
        "script": [
            {"ar": "أَهْلًا فِيك! عِنْدَك حَجْز؟", "uz": "Xush kelibsiz! Broningiz bormi?"},
            {"ar": "تَمَام، لَقِيت حَجْزَك. غُرْفَة رَقْم ٣٠٥ فِي الطَّابِق الثَّالِث.", "uz": "Yaxshi, broningizni topdim. 305-xona, 3-qavat."},
            {"ar": "وَلَا يْهِمّك، بَنْغَيِّر لَك الغُرْفَة حَالًا.", "uz": "Xavotir olmang, xonangizni hozir almashtiramiz."},
            {"ar": "هَذَا المِفْتَاح الجَدِيد. أَيّ خِدْمَة، اِتَّصِل فِينَا. تَشَرَّفْنَا!", "uz": "Mana yangi kalit. Har qanday xizmat kerak bo'lsa, qo'ng'iroq qiling!"},
        ],
    },
    "shopping": {
        "title_uz": "Bozor sotuvchisi",
        "emoji": "🛍️",
        "desc_uz": "Bozorda sovg'a oling — savdolashib arzonlashtiring.",
        "system": (
            "Sen Makka bozoridagi sotuvchisan. O'quvchi (A2) xaridor. HIJOZIY lahjada "
            "SODDA javob ber. Narx aytasan, savdolashasan, oxirida rozi bo'lasan. "
            "Do'stona va hazil aralash. Har javobing ARABCHA."
        ),
        "script": [
            {"ar": "تَفَضَّل يَا غَالِي! شُوف الهَدَايَا، كُلّهَا حِلْوَة.", "uz": "Marhamat, aziz! Sovg'alarni ko'ring, hammasi chiroyli."},
            {"ar": "هَذِي بِمِئَة رِيَال، أَصْلِيَّة وَجُودَة عَالِيَة.", "uz": "Bu 100 riyol, asl va sifatli."},
            {"ar": "طَيِّب، عَشَان خَاطْرَك، تَمَانِين. آخِر كَلَام!", "uz": "Mayli, siz uchun 80. Oxirgi narx!"},
            {"ar": "خَلَاص، خُذهَا بِسَبْعِين. مَبْرُوك، اللَّه يِبَارِك فِيك!", "uz": "Bo'ldi, 70 ga oling. Muborak bo'lsin!"},
        ],
    },
}


def scenario_list() -> list[dict]:
    return [
        {"id": k, "title_uz": v["title_uz"], "emoji": v["emoji"], "desc_uz": v["desc_uz"]}
        for k, v in SCENARIOS.items()
    ]


def opening(scenario_id: str) -> dict | None:
    sc = SCENARIOS.get(scenario_id)
    if not sc:
        return None
    first = sc["script"][0]
    return {"ar": first["ar"], "uz": first["uz"], "ai": False, "done": False}


async def reply(scenario_id: str, history: list[dict]) -> dict:
    """history: [{role:'user'|'assistant', content}]. Keyingi rol javobini qaytaradi."""
    sc = SCENARIOS.get(scenario_id)
    if not sc:
        return {"ar": "", "uz": "Vaziyat topilmadi.", "ai": False, "done": True}

    user_turns = sum(1 for m in history if m.get("role") == "user")

    # Kredit bo'lsa — Claude jonli o'ynaydi
    if settings.anthropic_api_key:
        try:
            from anthropic import AsyncAnthropic

            client = AsyncAnthropic(api_key=settings.anthropic_api_key)
            msgs = [
                {"role": m["role"], "content": m["content"]}
                for m in history
                if m.get("content")
            ]
            resp = await client.messages.create(
                model="claude-opus-4-8",
                max_tokens=400,
                system=(
                    sc["system"]
                    + "\n\nJavob formati: avval roldagi arabcha javobing, keyin yangi "
                    "qatorda `[UZ] <o'zbekcha qisqa tarjima yoki tuzatish>`. Suhbat "
                    "tabiiy tugasa, oxirida `[TAMOM]` yoz."
                ),
                messages=msgs or [{"role": "user", "content": "(suhbatni boshla)"}],
            )
            text = "".join(b.text for b in resp.content if b.type == "text").strip()
            done = "[TAMOM]" in text
            text = text.replace("[TAMOM]", "").strip()
            ar, uz = text, ""
            if "[UZ]" in text:
                ar, uz = text.split("[UZ]", 1)
                ar, uz = ar.strip(), uz.strip()
            return {"ar": ar, "uz": uz, "ai": True, "done": done}
        except Exception:
            pass  # kredit/xato — skriptga tushamiz

    # Zaxira: skript bo'yicha keyingi turn
    idx = min(user_turns, len(sc["script"]) - 1)
    turn = sc["script"][idx]
    done = idx >= len(sc["script"]) - 1
    return {"ar": turn["ar"], "uz": turn["uz"], "ai": False, "done": done}
