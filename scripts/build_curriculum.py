"""content/curriculum.json ni yasaydi — 160 darsning meta-ma'lumoti.

Manba: docs/ARABIY_CURRICULUM.md (§5-8 jadvallari).
Ishlatish: python scripts/build_curriculum.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "content" / "curriculum.json"

# Har qator: (title_uz, topic/grammatika, so'z_mo'ljali, eslatma, hejazi)
# type: exam qatorlari alohida belgilanadi.

A0 = [  # module ranglari: 1-9 letters, 10-17 harakat, 18 reading, 19-21 pronunciation, 22 roots-intro, 23-24 workshop, 25 exam
    ("Arab alifbosi", "O'ngdan chapga yozuv, 28 harf bilan umumiy tanishuv", 5, "Motivatsiya: o'zbekchadagi arabcha so'zlar", False),
    ("Harf oilasi 1: ب ت ث ن ي", "Nuqta farqi bilan ajratish", 6, "Birinchi o'qiladigan so'z: بَيْت", False),
    ("Harf oilasi 2: ج ح خ", "خ tovushi o'zbekda bor (x)", 6, "باب · بِنْت", False),
    ("Harf oilasi 3: د ذ ر ز", "Ulanmaydigan harflar bilan tanishuv", 6, "دَرْس · وَرْد", False),
    ("Harf oilasi 4: س ش ص ض", "Qalin (emfatik) harflar kirish", 6, "شَمْس", False),
    ("Harf oilasi 5: ط ظ ع غ", "ع — eng qiyin tovush; غ o'zbekda bor (g')", 6, "", False),
    ("Harf oilasi 6: ف ق ك ل م ه و", "ق tovushi o'zbekda bor (q)", 8, "قَلَم · كِتاب", False),
    ("Ulanish shakllari", "Harfning boshi / o'rtasi / oxiri shakllari", 6, "Interaktiv mashqlar", False),
    ("Ulanmaydigan 6 harf", "ا د ذ ر ز و dan keyin uzilish", 6, "So'z ichida bo'linish", False),
    ("Qisqa unlilar", "Fatha · kasra · damma", 8, "كَتَبَ / كُتُب farqi", False),
    ("Sukun", "Harakatsiz harf", 6, "مَكْتَب", False),
    ("Shadda", "Ikkilangan harf", 6, "مُدَرِّس", False),
    ("Tanvin", "ً ٍ ٌ — noaniqlik belgisi", 6, "كِتابٌ", False),
    ("Cho'ziq unlilar (madd)", "ا و ي cho'zish vazifasida", 8, "كِتاب · نور · بيت", False),
    ("Ta marbuta (ة)", "Muannaslik belgisi", 6, "مَدْرَسة", False),
    ("Hamza", "ء أ إ ؤ ئ shakllari", 6, "أَب · إِسْلام", False),
    ("Alif maqsura (ى)", "ى va ي farqi", 5, "مُوسى", False),
    ("Quyosh va oy harflari", "ال artikli assimilyatsiyasi: الشَّمْس vs القَمَر", 8, "Aniqlik artikli", False),
    ("Talaffuz 1: ع ح", "O'zbekda YO'Q tovushlar ustaxonasi", 0, "Audio + ovozli takrorlash (shadowing)", False),
    ("Talaffuz 2: ص ض ط ظ", "Qalin harflar: س/ص · ت/ط solishtiruv", 0, "Minimal juftliklar", False),
    ("Talaffuz 3: ق خ غ", "O'zbekda BOR tovushlar — motivatsion dars", 0, "qalam=قلم, xabar=خبر, g'oya kabi ko'priklar", False),
    ("O'zak (جذر) tushunchasi", "3 harfli o'zak tizimi kirish", 10, "O'zbekcha ko'prik jadvali: kitob-maktab-kotib", False),
    ("O'qish ustaxonasi", "50 so'zni ravon o'qish", 15, "Vaqtli o'qish mashqi", False),
    ("Qo'lda yozish", "Harf yozish tartibi (yo'nalishlar)", 0, "Ko'rsatma + mashq varaqlari", False),
    ("A0 IMTIHONI", "4 ko'nikma bo'yicha yakuniy imtihon", 0, "80% → Sertifikat A0", False),
]

A1 = [  # 1-8 nominal, 9-16 past, 17-24 present, 25-32 nouns, 33-40 daily
    ("Oddiy tasdiq gap tuzaman", "Ismli gap: مُبْتَدَأ + خَبَر", 10, "", False),
    ("Kim haqida gapirayotganimni aytaman", "Kishilik olmoshlari (munfasil)", 10, "", False),
    ("«Bu / anavi» deb ko'rsataman", "هذا · هذه · ذلك · تلك", 10, "", False),
    ("Aniq va noaniqni farqlayman", "ال vs tanvin", 8, "", False),
    ("Erkak/ayol so'zni ajrataman", "Muzakkar / muannas (ة)", 10, "", False),
    ("Narsani tasvirlayman", "Sifat va moslashuv (النَّعْت)", 10, "", False),
    ("Savol beraman", "ما · مَن · أين · كيف · هل · أ", 10, "", False),
    ("Salomlashaman, tanishaman", "Amaliy muloqot darsi", 10, "", True),
    ("«U yozdi / u (ayol) yozdi»", "Ma'zi: هو / هي — كَتَبَ / كَتَبَتْ", 10, "", False),
    ("«Sen yozding»", "Ma'zi: أنتَ / أنتِ — كَتَبْتَ / كَتَبْتِ", 10, "", False),
    ("«Men yozdim / biz yozdik»", "Ma'zi: أنا / نحن — كَتَبْتُ / كَتَبْنا", 10, "", False),
    ("Ko'plikda gapiraman", "Ma'zi: هم / هنّ / أنتم — كَتَبوا", 10, "", False),
    ("Ma'zi to'liq jadval", "14 shakl + intensiv drill", 8, "Konjugatsiya drill", False),
    ("Kim nima qilganini aytaman", "Fe'lli gap: فِعْل + فاعِل + مَفْعول", 10, "", False),
    ("«Qilmadim»", "Inkor: ما + ma'zi", 8, "", False),
    ("Bir o'zakdan 5 so'z yasayman", "فَعَلَ → فاعِل → مَفْعول → مَفْعَل", 10, "O'zak-vazn ustaxonasi", False),
    ("Muzori' prefikslarini bilaman", "أ ت ي ن — «ATIN» qoidasi", 8, "", False),
    ("«U yozadi»", "Muzori': يَكْتُبُ / تَكْتُبُ", 10, "", False),
    ("«Sen yozasan»", "Muzori': أنتَ / أنتِ", 10, "", False),
    ("«Men yozaman / biz yozamiz»", "Muzori': أنا / نحن", 10, "", False),
    ("Muzori' to'liq jadval", "14 shakl + drill", 8, "Konjugatsiya drill", False),
    ("«Qilmayapman»", "Inkor: لا + muzori'", 8, "", False),
    ("Kelasi zamon", "سَـ / سَوْفَ", 10, "", False),
    ("Ma'zi vs Muzori'", "Aralash solishtirma drill", 8, "", False),
    ("Ikkita narsa haqida gapiraman", "Ikkilik son (المُثَنّى): كِتابان", 10, "", False),
    ("Ko'plik yasayman", "Sog'lom ko'plik: مُعَلِّمون / مُعَلِّمات", 10, "", False),
    ("Notekis ko'plikni tanib olaman", "Singan ko'plik — asosiy vaznlar", 12, "", False),
    ("«Kimningdir kitobi»", "Idafa (الإضافة)", 10, "", False),
    ("«Mening kitobim»", "Ulangan olmoshlar: كِتابي · كِتابُكَ", 10, "", False),
    ("Joyni ko'rsataman", "Predloglar: في · على · من · إلى · مع · عن · بـ · لـ", 12, "", False),
    ("So'z oxiridagi harakatni tushunaman", "I'rob kirish: رَفْع / نَصْب / جَرّ", 8, "", False),
    ("Turli inkorni bilaman", "لَيْسَ · ما · لا · لَمْ · لَنْ", 8, "", False),
    ("Oilam haqida gapiraman", "Oila va qarindoshlik so'zlari", 12, "", False),
    ("1–10 sanayman", "Sonlar 1-10 + qutbiylik kirish", 10, "", False),
    ("Narx va yoshni aytaman", "Sonlar 11-100", 10, "", True),
    ("Vaqtni aytaman", "Soat, hafta kunlari, oylar, namoz vaqtlari", 12, "", False),
    ("Ovqat buyurtma qilaman", "Restoran leksikasi va muloqoti", 12, "", True),
    ("Yo'l so'rayman", "Yo'nalish va transport", 12, "", True),
    ("Takrorlash", "O'zak/vazn ustaxonasi — A1 materiallari", 8, "", False),
    ("A1 IMTIHONI", "4 ko'nikma bo'yicha yakuniy imtihon", 0, "80% → Sertifikat A1", False),
]

A2 = [  # 1-9 sarf, 10-21 verb-forms, 22-27 weak-verbs, 28-35 grammar-ext, 36-47 saudi, 48-53 skills, 54 exam
    ("Sarf nima? 14 shakl tizimi", "غائب/مخاطب/متكلّم × muzakkar/muannas × mufrad/musanna/jam'", 10, "Butun arab tilining kaliti", False),
    ("Moziy fe'li: 14 shakl to'liq", "الماضي — كَتَبَ dan كَتَبْنَا gacha", 10, "Tasniya (ikkilik) shakllari yangi", False),
    ("Moziy: turli fe'llar bilan mashq", "ذَهَبَ · شَرِبَ · سَمِعَ · تَعَلَّمَ", 10, "", False),
    ("Muzori' fe'li: 14 shakl to'liq", "المضارع — يَكْتُبُ dan نَكْتُبُ gacha", 10, "ATIN prefikslari + oxirgi qo'shimchalar", False),
    ("Muzori': boblar bilan", "يَتَعَلَّمُ · يَسْتَيْقِظُ · يُسَافِرُ · يَسْتَخْدِمُ", 10, "", False),
    ("Sarf ustaxonasi: moziy ⇄ muzori'", "Ikki zamon o'rtasida almashtirish drilli", 10, "Interaktiv wow-dars", False),
    ("Alohida olmoshlar (14 ta)", "الضمائر المنفصلة — هُوَ … نَحْنُ", 10, "A1 dagi 8 tasi + tasniya to'ldiriladi", False),
    ("Birikuvchi olmoshlar (14 ta)", "الضمائر المتصلة — كِتَابُهُ · كِتَابِي", 10, "Ot + fe'l + predlog bilan", False),
    ("Ko'rsatish olmoshlari to'liq", "أسماء الإشارة — yaqin/uzoq, tasniya bilan", 10, "هَذَانِ · هَاتَانِ · أُولَئِكَ", False),
    ("Fe'l boblari: umumiy ko'rinish", "I-X tizimi — bitta o'zakdan 10 xil ma'no", 8, "", False),
    ("II bob: kuchaytirish", "فَعَّلَ — عَلَّمَ (o'rgatdi)", 10, "muallim · ta'lim · mudarris ko'prigi", False),
    ("III bob: o'zaro harakat", "فاعَلَ — شاهَدَ", 10, "mushohada", False),
    ("IV bob: sababiyat", "أَفْعَلَ — أَسْلَمَ", 10, "islom · muslim · e'lon", False),
    ("V bob: II ning qaytimi", "تَفَعَّلَ — تَعَلَّمَ (o'rgandi)", 10, "tashakkur · tafakkur", False),
    ("VI bob: o'zaro", "تَفاعَلَ — تَعاوَنَ", 10, "taovun", False),
    ("VII bob: majhul/qaytim", "اِنْفَعَلَ — اِنْكَسَرَ", 10, "inqilob", False),
    ("VIII bob: qaytim", "اِفْتَعَلَ — اِجْتَمَعَ", 10, "ijtimoiy · ehtirom · intizor", False),
    ("X bob: talab qilish", "اِسْتَفْعَلَ — اِسْتَغْفَرَ", 10, "istiqlol · mustaqbal · istig'for", False),
    ("Masdar", "Har bob uchun masdar vazni: تَفْعيل · إِفْعال · اِسْتِفْعال", 10, "ta'lim · islom · istiqlol", False),
    ("Ism fo'il / maf'ul", "مُعَلِّم / مُعَلَّم — bajaruvchi/bajarilgan", 10, "muallim · muslim · mustaqbal", False),
    ("BOB USTAXONASI", "Bitta o'zakdan 12 so'z: ع-ل-م", 12, "Interaktiv wow-dars", False),
    ("Illatli fe'l nima?", "Turlari bilan umumiy tanishuv", 8, "", False),
    ("Misol fe'llar", "مِثال (boshi و/ي): وَصَلَ · وَجَدَ", 10, "", False),
    ("Ajvaf fe'llar", "أَجْوَف (o'rtasi و/ي): قالَ · كانَ · زارَ", 10, "", False),
    ("Naqis fe'llar", "ناقِص (oxiri و/ي): مَشى · دَعا · بَنى", 10, "", False),
    ("Muzoaf va mahmuz", "مُضاعَف: مَرَّ · رَدَّ / مَهْموز: سَأَلَ · قَرَأَ", 10, "", False),
    ("Illatli fe'llar drilli", "Aralash mashqlar", 8, "", False),
    ("«Edi / bo'ldi»", "كانَ va opa-singillari", 10, "", False),
    ("Ta'kid bilan gapiraman", "إنَّ va opa-singillari", 10, "", False),
    ("Buyruq beraman", "Amr (الأمر): اُكْتُبْ!", 10, "", False),
    ("«Yozildi» deyman", "Majhul nisbat — kirish", 10, "", False),
    ("Solishtiraman", "أَفْعَل مِن / الأَفْعَل", 10, "", False),
    ("Katta sonlarni aytaman", "100-1000 + to'liq qutbiylik qoidasi", 10, "", False),
    ("Tartibni aytaman", "الأوّل · الثاني · الثالث", 10, "", False),
    ("Vaqt/joyni aniqlayman", "Zarf (ظرف الزمان والمكان)", 10, "", False),
    ("Aeroport", "Pasport, viza, bojxona muloqoti", 12, "", True),
    ("Transport", "Taksi, Haramayn poyezdi, avtobus", 12, "", True),
    ("Mehmonxona", "Bron, check-in, muammo hal qilish", 12, "", True),
    ("Restoran", "Buyurtma, halol, hisob", 12, "", True),
    ("Xarid", "Bozor, savdolashish, narx", 12, "", True),
    ("Dorixona / shifokor", "Og'riq, dori, favqulodda tibbiy holat", 12, "", True),
    ("Bank / to'lov", "Valyuta, karta, mada tizimi", 12, "", True),
    ("Umra lug'ati", "إحرام · طواف · سعي · تلبية", 12, "Diniy atamalar aniq va hurmatli", True),
    ("Masjid odobi", "Namoz vaqti, azon, iqoma, safar namozi", 12, "", True),
    ("Makka va Madina", "Joylar, yo'nalishlar, belgilar", 12, "", True),
    ("Favqulodda holat", "Politsiya, kasalxona, yo'qotish", 12, "", True),
    ("Hijoziy ustaxonasi", "Eng kerakli 100 ibora — intensiv", 15, "Hijoziy deck SRS", True),
    ("O'qish: belgi va menyu", "Real fotosuratlardan o'qish", 8, "", False),
    ("O'qish: qisqa hikoya", "Harakat kamayadi", 8, "", False),
    ("Tinglash: real suhbat", "Sekin → normal tezlik", 6, "", False),
    ("Yozish: xabar va xat", "Qisqa xat, tavsif", 6, "", False),
    ("Gapirish: rol o'yinlari", "AI bilan 10 vaziyat", 6, "", False),
    ("Umumiy takrorlash", "A2 materiallari bo'ylab", 6, "", False),
    ("A2 IMTIHONI", "4 ko'nikma bo'yicha yakuniy imtihon", 0, "80% → Sertifikat A2", False),
]

B1 = [  # 1-14 adv-grammar, 15-26 vocab, 27-34 quran-hadith, 35-46 skills, 47-50 exam
    ("Majhul nisbat — to'liq", "Har bob uchun majhul shakllar", 10, "", False),
    ("Nisbiy olmoshlar", "الذي · التي · الذين · اللاتي", 10, "", False),
    ("Sifatlovchi gap", "Noaniq ot bilan sifat gap", 10, "", False),
    ("Shart gap 1", "إذا (real shart)", 10, "", False),
    ("Shart gap 2", "إنْ · مَنْ · ما", 10, "", False),
    ("Shart gap 3", "لَوْ (noreal shart)", 10, "", False),
    ("Hol", "الحال konstruksiyasi", 10, "", False),
    ("Tamyiz", "التمييز konstruksiyasi", 10, "", False),
    ("Istisno", "إلّا · غير · سوى", 10, "", False),
    ("Maf'ul mutlaq", "Ta'kid uchun masdar", 10, "", False),
    ("Maf'ul li-ajlih", "Sabab holati", 10, "", False),
    ("Muzori' mansub", "أنْ · لَنْ · كَيْ · حتّى", 10, "", False),
    ("Muzori' majzum", "لَمْ · لا الناهية", 10, "", False),
    ("To'liq i'rob ustaxonasi", "Gap tahlili amaliyoti", 8, "", False),
    ("Singan ko'pliklar — tizimli", "Asosiy 20 vazn", 15, "", False),
    ("Ish va kasb", "Mavzuviy lug'at", 12, "", False),
    ("Ta'lim", "Mavzuviy lug'at", 12, "", False),
    ("Salomatlik", "Mavzuviy lug'at", 12, "", False),
    ("Biznes", "Mavzuviy lug'at", 12, "", False),
    ("Texnologiya", "Mavzuviy lug'at", 12, "", False),
    ("OAV", "Mavzuviy lug'at", 12, "", False),
    ("Iqtisod", "Mavzuviy lug'at", 12, "", False),
    ("Sayohat — kengaytirilgan", "Mavzuviy lug'at", 12, "", False),
    ("Tabiat", "Mavzuviy lug'at", 12, "", False),
    ("Sport", "Mavzuviy lug'at", 12, "", False),
    ("Hissiyot", "Mavzuviy lug'at", 12, "", False),
    ("Qur'on tili", "MSA'dan farqlari", 10, "Diniy kontent — aniq va hurmatli", False),
    ("100 Qur'oniy so'z", "Eng ko'p uchraydigan so'zlar (matnning ~40%)", 15, "", False),
    ("Qisqa suralar tahlili 1", "So'zma-so'z, o'zak bilan", 10, "Sura/oyat raqamlari aniq", False),
    ("Qisqa suralar tahlili 2", "So'zma-so'z, o'zak bilan", 10, "Sura/oyat raqamlari aniq", False),
    ("Hadis matni tuzilishi", "Isnod + matn", 10, "", False),
    ("Arba'in namunalari", "an-Nawawiy to'plamidan", 10, "", False),
    ("Duo va zikr matnlari", "Grammatik tahlil", 10, "", False),
    ("Diniy atamalar lug'ati", "Asosiy terminlar", 12, "", False),
    ("O'qish: yangilik 1", "Soddalashtirilgan maqola", 8, "", False),
    ("O'qish: yangilik 2", "Soddalashtirilgan → original", 8, "", False),
    ("O'qish: yangilik 3", "Original maqola", 8, "", False),
    ("O'qish: yangilik 4", "Original maqola + tahlil", 8, "", False),
    ("Tinglash: podkast", "Parcha + savollar", 6, "", False),
    ("Tinglash: intervyu", "Parcha + savollar", 6, "", False),
    ("Tinglash: xabar", "Yangiliklar formati", 6, "", False),
    ("Yozish: rasmiy xat", "Format va iboralar", 6, "", False),
    ("Yozish: insho", "Fikr bayoni", 6, "", False),
    ("Yozish: xulosa", "Matnni qisqartirish", 6, "", False),
    ("Gapirish: taqdimot", "AI bilan mashq", 6, "", False),
    ("Gapirish: munozara", "Fikr bildirish, AI bilan", 6, "", False),
    ("Takrorlash: grammatika", "B1 grammatikasi bo'ylab", 6, "", False),
    ("Takrorlash: lug'at + o'zak", "B1 lug'ati bo'ylab", 8, "", False),
    ("Sinov imtihoni", "Mashq rejimidagi to'liq imtihon", 0, "", False),
    ("B1 IMTIHONI", "4 ko'nikma bo'yicha yakuniy imtihon", 0, "80% → Sertifikat B1", False),
]


def module_for(level: str, order: int) -> str:
    if level == "A0":
        if order <= 9: return "letters"
        if order <= 17: return "harakat"
        if order == 18: return "reading"
        if order <= 21: return "pronunciation"
        if order == 22: return "roots-intro"
        if order <= 24: return "workshop"
        return "exam"
    if level == "A1":
        if order <= 8: return "nominal-sentence"
        if order <= 16: return "past-tense"
        if order <= 24: return "present-tense"
        if order <= 32: return "noun-system"
        if order <= 39: return "daily-life"
        return "exam"
    if level == "A2":
        if order <= 9: return "sarf"
        if order <= 21: return "verb-forms"
        if order <= 27: return "weak-verbs"
        if order <= 35: return "grammar-ext"
        if order <= 47: return "saudi"
        if order <= 53: return "skills"
        return "exam"
    # B1
    if order <= 14: return "adv-grammar"
    if order <= 26: return "vocab"
    if order <= 34: return "quran-hadith"
    if order <= 46: return "skills"
    if order <= 49: return "review"
    return "exam"


HARAKAT_BY_LEVEL = {
    "A0": "full",
    "A1": "full",
    "A2": "new_words_only",
    "B1": "ambiguous_only",
}


def build() -> dict:
    lessons = []
    for level, rows in (("A0", A0), ("A1", A1), ("A2", A2), ("B1", B1)):
        prefix = level.lower()
        for i, (title, topic, words, note, hejazi) in enumerate(rows, start=1):
            lid = f"{prefix}-{i:02d}"
            module = module_for(level, i)
            entry = {
                "id": lid,
                "level": level,
                "module": module,
                "order": i,
                "title_uz": title,
                "topic": topic,
                "words_target": words,
                "note": note,
                "hejazi": hejazi,
                "harakat_level": HARAKAT_BY_LEVEL[level],
                "type": "exam" if module == "exam" else "lesson",
                "prerequisites": [f"{prefix}-{i-1:02d}"] if i > 1 else [],
            }
            lessons.append(entry)

    counts = {}
    for l in lessons:
        counts[l["level"]] = counts.get(l["level"], 0) + 1

    return {
        "version": "1.0",
        "source": "docs/ARABIY_CURRICULUM.md",
        "counts": counts,
        "lessons": lessons,
    }


if __name__ == "__main__":
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    data = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    total = sum(data["counts"].values())
    print(f"curriculum.json yozildi: {total} dars {data['counts']}")
    assert total == 169, f"169 emas: {total}"
