# ARABIY — To'liq O'quv Dasturi (Curriculum Spec v1.0)

**Loyiha:** `arabiy.digitalcfo.uz` — Telegram Mini App (FastAPI + aiogram + SRS)
**Auditoriya:** O'zbek tilida so'zlashuvchilar, Saudiya safari (umra / haj / ish) + rasmiy arab tili
**Maqsad:** o'qish · gapirish · yozish

> Bu hujjat — **spetsifikatsiya**. Kontent generatsiya, dars tuzilmasi, imtihon va sertifikat tizimi uchun yagona haqiqat manbasi.

---

## 0. TL;DR — Asosiy qarorlar

| Savol | Qaror | Sabab |
|---|---|---|
| **Qaysi arab tili?** | **MSA (فصحى) umurtqa + Hijoziy qatlam** | Makka/Madina/Jiddada Hijoziy gapiriladi. Lekin belgi, hujjat, Qur'on, imtihon — MSA. Ikkalasi kerak, **aralashtirmasdan**. |
| **Fe'lga qancha vaqt?** | **~26% (42 dars)** | Arab tilining eng katta tog'i. Sizning eski rejangizda "Verb forms" = 1 dars edi. |
| **O'zak–vazn tizimi?** | **Dasturning yadrosi**, A0 #22 dan boshlab har darsda | Eng katta raqobat ustunligi. Eski rejada umuman yo'q edi. |
| **Nechta dars?** | **160** (A0:25, A1:40, A2:45, B1:50) | Halol hisob. B2 — 2-bosqich, obuna mahsuloti. |
| **Sertifikat?** | Har daraja oxirida: **80%+** VA har ko'nikmada **min 60%** | Bitta ko'nikma hisobiga o'tib ketishning oldini oladi. |
| **Harakat?** | A0:100% → B1:minimal, **bosilsa ko'rinadi** | Real arab matni harakatsiz. Bunga tayyorlash kerak. |

---

## 1. STRATEGIYA

### 1.1 Diglossiya — hal qilinishi shart bo'lgan masala

Arab tili **ikki qatlamli**: yozma til (فصحى) va gapiriladigan lahjalar. Qohirada kafeda hech kim MSA'da gapirmaydi. Eski rejangiz ikkalasini bir yo'lda va'da qilardi — natijada ikkalasini ham bermasdi.

**Qaror:**

| Qatlam | Nima uchun | Qayerda |
|---|---|---|
| **MSA (الفصحى)** | Grammatika, o'qish, yozish, Qur'on, imtihon, sertifikat | **Barcha darslarda** |
| **Hijoziy (حجازي)** | Makka/Madina/Jidda ko'chasida gapirish | Faqat funksional darslarda 🇸🇦 blok |

**Qoida:** grammatika/yozuv/imtihon — faqat MSA. Hijoziy — faqat og'zaki qatlam, alohida SRS deck. Farq o'rganuvchiga **ochiq aytiladi**: *"Kitobda shunday, ko'chada bunday."*

### 1.2 Halol vaqt hisobi

FSI tasnifi bo'yicha arab tili — **IV toifa** (eng qiyin guruh).

| Daraja | Jahon standarti | Bizda |
|---|---|---|
| A1 | ~100 soat | 65 dars (A0+A1) |
| A2 | ~200 soat (jami) | 110 dars |
| B1 | ~400 soat (jami) | 160 dars |
| B2 | ~700+ soat (jami) | **2-bosqich** |

**160 dars × 30–40 daq ≈ 90–110 soat** ilova vaqti + SRS + tashqi mashq.

**Halol va'da:** bu dastur **mustahkam A2 / B1 ostonasi**ga olib chiqadi:
- Saudiyada mustaqil harakatlanadi
- Harakatsiz oddiy matnni o'qiydi
- Fikrini yozma va og'zaki ifodalaydi
- Qur'on/hadis matnining tuzilishini tushunadi

**B2 ni birinchi versiyada VA'DA QILMANG.** 150 darsda B2 bermoq — foydalanuvchi ishonchini yo'qotish. Kam va'da qiling, ko'p bering.

### 1.3 O'zbek o'rganuvchining yashirin ustunligi

Bu — mahsulotning **eng katta farqlovchi xususiyati**.

| Ustunlik | Ishlatilishi |
|---|---|
| Minglab arabcha o'zlashma (kitob, maktab, hukm, ilm, sabr, mustaqbal...) | **O'zak–vazn tizimi** (3-bo'lim) |
| ق، خ، غ tovushlari o'zbek tilida **BOR** | Talaffuz darsi — motivatsion moment (rus/ingliz uchun bu qiyin) |
| Ko'pchilik arab yozuvini o'qiy oladi (Qur'on darsi) | **Ikkinchi kirish yo'li** |
| Islomiy lug'at tanish | B1 Qur'on/hadis moduli |

**Birinchi haftadagi maqsad:** o'rganuvchi *"men allaqachon 500 ta arabcha so'z bilar ekanman"* degan hissiyotga kelsin.

### 1.4 Ikkita kirish yo'li

```
"Arab harflarini bilmayman"           → A0 to'liq (25 dars)
"Qur'on o'qiyman, ma'nosini bilmayman" → A0 tez tekshiruv (5 dars) → A1
"Biroz bilaman"                        → Joylashtiruv testi (15 savol)
```

Bot allaqachon boshlang'ich suhbat orqali daraja aniqlaydi — shuni shu uch yo'lga ulang.

---

## 2. PEDAGOGIK TAMOYILLAR

Bular **har bir darsga** taalluqli va buzilmaydi.

### 2.1 Ko'nikmalar ajratilmaydi — integratsiya qilinadi

❌ **Eski xato:** 28 ta grammatika darsi → keyin 3 ta "Listening" darsi
✅ **To'g'ri:** har darsda 4 ko'nikma ham bor, kichik dozalarda

**Har bir darsning majburiy tarkibi:**

```
1 × "nima qila olaman" (can-do)
1 × grammatika nuqtasi (kichik, hazm bo'ladigan)
8–12 × yangi so'z            → SRS
1–2 × o'zak                  → o'zbekcha ko'prik
O'qish mashqi (2–5 gap)
Tinglash mashqi (audio + savol)
Gapirish mashqi (ovozli xabar → AI baho)
Yozish mashqi (1–3 gap)
Mikro-test (5–7 savol)
```

### 2.2 Dars sarlavhasi = **qila oladigan ish**

❌ "Idofa konstruksiyasi"
✅ "Nimadir kimniki ekanini ayta olaman" *(ichida: الإضافة)*

### 2.3 Fe'llar — umumiy vaqtning 26%

| Modul | Darslar |
|---|---|
| Ma'zi (o'tgan zamon) — to'liq paradigma | A1: 8 |
| Muzori' (hozirgi zamon) — to'liq paradigma | A1: 8 |
| **Boblar I–X (الأوزان)** | A2: 12 |
| Illatli fe'llar (مثال/أجوف/ناقص/مضاعف) | A2: 6 |
| Majhul, amr, mansub, majzum | A2–B1: 8 |
| **Jami** | **42 dars** |

### 2.4 O'tgan zamon **birinchi**, hozirgi zamon ikkinchi

Eski rejada teskari edi. الماضي — lug'aviy asos (lug'atda fe'l shu shaklda beriladi) va morfologik jihatdan soddaroq: prefiks yo'q, faqat suffiks.

### 2.5 Lug'at: 70% chastota + 30% mavzu

Arab tilidagi eng ko'p uchraydigan **100 so'z** oddiy matnning ~50% ini qoplaydi. "Ranglar", "Kasblar" — kam uchraydigan so'zlar, ularni erta bermang.

| Daraja | Faol lug'at (jami) |
|---|---|
| A0 | ~150 |
| A1 | ~800 |
| A2 | ~2000 |
| B1 | ~3800 |

### 2.6 Harakat (تشكيل) bosqichma-bosqich olib tashlanadi

| Daraja | Harakat |
|---|---|
| A0 | 100% |
| A1 | 100% |
| A2 | Faqat yangi so'zlarda |
| B1 | Faqat ikkiyoqlama o'qiladiganlarida |
| B2 | Yo'q |

**UI (majburiy):** har qanday darajada so'zga **bosilsa** — harakat + ma'no + o'zak + vazn ko'rinadi (tap-to-reveal).

### 2.7 Tashlab ketish nuqtalari va yechimlar

| Xavf | Yechim |
|---|---|
| A0: 6 dars harf yodlash, hech nima o'qiy olmaydi | **A0 #2 dan o'qiladigan so'z:** بَيْت، باب |
| A1: ma'zi 14 shakl birdan | **3 shaxsdan boshlang** (هو/هي/أنا), qolgani asta |
| A2: boblar I–X | Har bobga **alohida dars** + o'zbekcha ko'prik |
| A2: sonlar qutbiyligi | Alohida 2 dars |
| B1: birinchi uzun matn | Uzunlik bosqichma-bosqich: 3 → 5 → 10 → 20 gap |

---

## 3. O'ZAK–VAZN TIZIMI (yadro)

Bu bo'lim yo'q bo'lsa — bot oddiy flashcard ilovasiga aylanadi.

### 3.1 Tushuncha

Arab tilida so'zlar **3 harfli o'zakdan** (جذر) **vaznlar** (أوزان) orqali yasaladi. Bu tizimni tushungan o'zbek o'rganuvchi lug'atni **5 barobar tez** o'zlashtiradi.

### 3.2 O'zbekcha ko'prik — birinchi 20 o'zak

| O'zak | Ma'no | Arabcha shakllar | **O'zbek tilida allaqachon bor** |
|---|---|---|---|
| ك-ت-ب | yozmoq | كِتاب · مَكْتَب · كاتِب · مَكْتوب · مَكْتَبة | kitob, maktab, kotib, maktub, kutubxona |
| د-ر-س | o'qimoq | دَرْس · مُدَرِّس · مَدْرَسة · تَدْريس | dars, mudarris, madrasa, tadris |
| ع-ل-م | bilmoq | عِلْم · عالِم · مُعَلِّم · تَعْليم · مَعْلومات | ilm, olim, muallim, ta'lim, ma'lumot |
| ح-ك-م | hukm qilmoq | حُكْم · حاكِم · حِكْمة · مَحْكَمة · حُكومة | hukm, hokim, hikmat, mahkama, hukumat |
| س-ل-م | omon bo'lmoq | سَلام · إِسْلام · مُسْلِم · سَلامة | salom, islom, muslim, salomatlik |
| ع-م-ل | ishlamoq | عَمَل · عامِل · مُعامَلة · اِسْتِعْمال | amal, omil, muomala, iste'mol |
| ف-ك-ر | fikrlamoq | فِكْر · مُفَكِّر · تَفْكير · تَفَكُّر | fikr, mutafakkir, tafakkur |
| ش-ك-ر | shukr qilmoq | شُكْر · شاكِر · تَشَكُّر | shukr, shokir, tashakkur |
| ق-ب-ل | qabul qilmoq | قَبول · قِبْلة · اِسْتِقْبال · **مُسْتَقْبَل** | qabul, qibla, istiqbol, **mustaqbal** |
| ط-ل-ب | so'ramoq | طَلَب · طالِب · مَطْلَب | talab, tolib, matlab |
| خ-ب-ر | xabar bermoq | خَبَر · مُخْبِر · إِخْبار · اِخْتِبار | xabar, muxbir, axborot |
| ج-م-ع | to'plamoq | جَمْع · جامِع · مَجْموعة · اِجْتِماع · جامِعة | jam', jome', majmua, ijtimoiy |
| ح-س-ب | hisoblamoq | حِساب · مُحاسِب · حاسوب | hisob, muhosib |
| ن-ظ-ر | qaramoq | نَظَر · مَنْظَر · نَظَرِيّة · اِنْتِظار | nazar, manzara, nazariya, intizor |
| ح-ر-ر | ozod qilmoq | حُرِّيّة · مُحَرِّر · تَحْرير | hurriyat, muharrir, tahrir |
| ع-د-ل | adolatli bo'lmoq | عَدْل · عادِل · عَدالة | adl, odil, adolat |
| ن-ظ-م | tartibga solmoq | نِظام · مُنَظَّم · تَنْظيم · نَظْم | nizom, muntazam, tanzim, nazm |
| ش-ه-د | guvohlik bermoq | شاهِد · شَهادة · شَهيد | shohid, shahodat, shahid |
| ق-ر-أ | o'qimoq | قِراءة · قُرْآن · قارِئ | qiroat, Qur'on, qori |
| س-ف-ر | sayohat qilmoq | سَفَر · مُسافِر · سَفير · سِفارة | safar, musofir, safir, elchixona |

### 3.3 Asosiy vaznlar (A1)

| Vazn | Ma'no | Namuna (ك-ت-ب) | O'zbekcha |
|---|---|---|---|
| فَعَلَ | asosiy fe'l | كَتَبَ | yozdi |
| فاعِل | bajaruvchi | كاتِب | **kotib** |
| مَفْعول | bajarilgan | مَكْتوب | **maktub** |
| مَفْعَل | **joy** | مَكْتَب | **maktab** |
| مَفْعَلة | joy (kengroq) | مَكْتَبة | **kutubxona** |
| فِعال | narsa | كِتاب | **kitob** |

### 3.4 Bob (باب) vaznlari (A2 moduli)

| Bob | Fe'l | Masdar | Ism fo'il | **O'zbekcha misol** |
|---|---|---|---|---|
| I | فَعَلَ | فَعْل | فاعِل | كاتِب → **kotib** |
| II | فَعَّلَ | تَفْعيل | مُفَعِّل | تَعْليم → **ta'lim** · مُدَرِّس → **mudarris** |
| III | فاعَلَ | مُفاعَلة | مُفاعِل | مُشاهَدة → **mushohada** |
| IV | أَفْعَلَ | إِفْعال | مُفْعِل | إِسْلام → **islom** · مُسْلِم → **muslim** |
| V | تَفَعَّلَ | تَفَعُّل | مُتَفَعِّل | تَشَكُّر → **tashakkur** · تَفَكُّر → **tafakkur** |
| VI | تَفاعَلَ | تَفاعُل | مُتَفاعِل | تَعاوُن → **taovun** |
| VII | اِنْفَعَلَ | اِنْفِعال | مُنْفَعِل | اِنْقِلاب → **inqilob** |
| VIII | اِفْتَعَلَ | اِفْتِعال | مُفْتَعِل | اِحْتِرام → **ehtirom** · اِجْتِماع → **ijtimoiy** |
| X | اِسْتَفْعَلَ | اِسْتِفْعال | مُسْتَفْعِل | اِسْتِقْلال → **istiqlol** · مُسْتَقْبَل → **mustaqbal** |

> **اِسْتِقْلال = istiqlol.** Bu ko'rsatilgan sekundda o'rganuvchi *"voy, men buni bilar ekanman!"* deydi. Aynan shu moment mahsulotni sotadi.

### 3.5 SRS kartochka turlari

| Tur | Old | Orqa |
|---|---|---|
| `word` | كِتاب | kitob · ism · o'zak: ك-ت-ب |
| `root` | ك-ت-ب | yozmoq → kitob, maktab, kotib, maktub, kutubxona |
| `pattern` | مَفْعَل | **JOY vazni** → maktab, madrasa, malʼab |
| `phrase` 🇸🇦 | وين المطعم؟ | Restoran qayerda? *(Hijoziy)* |

Hijoziy va MSA — **alohida deck**. Aralashtirmang.

### 3.6 🔬 Root Lab — "wow" funksiyasi

Alohida ekran. O'zak tanlanadi → yasalgan so'zlar **daraxt** ko'rinishida → har biriga bosilsa audio + ma'no + o'zbekcha ko'prik.

Bu ekranni **ekran suratiga oladigan** qilib dizayn qiling. Bu — bepul marketing.

---

## 4. 🇸🇦 HIJOZIY QATLAM

Har bir funksional darsda majburiy blok:

```
📖 Rasmiy (فصحى)  →  🇸🇦 Saudiyada shunday deyiladi
```

| MSA | Hijoziy | Talaffuz | O'zbekcha |
|---|---|---|---|
| ماذا؟ | إيش؟ | esh | nima? |
| أين؟ | وين؟ | wen | qayerda? |
| لماذا؟ | ليش؟ | lesh | nega? |
| أُريدُ | أبغى / أبي | abgha / abi | xohlayman |
| هل تُريد؟ | تبغى؟ | tabgha | xohlaysanmi? |
| الآن | دحين | daḥīn | hozir |
| نعم | أيوه | aywa | ha |
| لا يوجد | ما فيه | ma fīh | yo'q |
| جيّد | زين / تمام | zēn / tamām | yaxshi |
| قليلاً | شوي | shwayya | ozgina |
| مباشرةً | على طول | ʿala ṭūl | to'g'riga / darhol |
| هيّا بنا | يالله | yalla | qani, ketdik |
| اِنتهى | خلاص | khalāṣ | tamom |
| لا بأس | معليش | maʿlēsh | zarari yo'q |
| كم الثمن؟ | بكم؟ | bikam | qanchaga? |

---

## 5. A0 — التأسيس · 25 dars

**Chiqish natijasi:** harakatli matnni ovoz chiqarib o'qiydi · 150 so'z · o'zak tushunchasi · yozadi.

| # | Sarlavha | Mavzu | So'z | Eslatma |
|---|---|---|---|---|
| 1 | Arab alifbosi | O'ngdan chapga, 28 harf | 5 | Motivatsiya: o'zbekchadagi arabcha so'zlar |
| 2 | Harf oilasi 1: ب ت ث ن ي | Nuqta farqi | 6 | **Birinchi so'z:** بَيْت |
| 3 | Harf oilasi 2: ج ح خ | خ o'zbekda **bor** | 6 | باب · بِنْت |
| 4 | Harf oilasi 3: د ذ ر ز | Ulanmaydigan harflar | 6 | دَرْس · وَرْد |
| 5 | Harf oilasi 4: س ش ص ض | Qalin harflar | 6 | شَمْس |
| 6 | Harf oilasi 5: ط ظ ع غ | ع — eng qiyin | 6 | غ o'zbekda **bor** |
| 7 | Harf oilasi 6: ف ق ك ل م ن ه و | ق o'zbekda **bor** | 8 | قَلَم · كِتاب |
| 8 | Ulanish shakllari | Boshi / o'rtasi / oxiri | 6 | Interaktiv |
| 9 | Ulanmaydigan 6 harf | ا د ذ ر ز و | 6 | So'z bo'linishi |
| 10 | Qisqa unlilar | Fatha · kasra · damma | 8 | كَتَبَ / كُتُب |
| 11 | Sukun | Harakatsiz harf | 6 | مَكْتَب |
| 12 | Shadda | Ikkilangan harf | 6 | مُدَرِّس |
| 13 | Tanvin | ً ٍ ٌ | 6 | كِتابٌ |
| 14 | Cho'ziq unlilar (madd) | ا و ي | 8 | كِتاب · نور · بيت |
| 15 | Ta marbuta (ة) | Muannaslik | 6 | مَدْرَسة |
| 16 | Hamza | ء أ إ ؤ ئ | 6 | أَب · إِسْلام |
| 17 | Alif maqsura (ى) | ى vs ي | 5 | مُوسى |
| 18 | Quyosh va oy harflari | الشَّمْس vs القَمَر | 8 | Aniqlik artikli ال |
| 19 | **Talaffuz 1:** ع ح | O'zbekda **YO'Q** | — | Audio + ovozli takrorlash |
| 20 | **Talaffuz 2:** ص ض ط ظ | Qalin harflar | — | س/ص · ت/ط solishtiruv |
| 21 | **Talaffuz 3:** ق خ غ | O'zbekda **BOR** | — | 🔥 Motivatsion dars |
| 22 | **O'zak (جذر) tushunchasi** | 3 harfli o'zak | 10 | 🔥 **Bridge jadvali (3.2)** |
| 23 | O'qish ustaxonasi | 50 so'zni ravon o'qish | 15 | Vaqtli |
| 24 | Qo'lda yozish | Harf yozish tartibi | — | Rasm → AI baho |
| 25 | **A0 IMTIHONI** | 4 ko'nikma | — | 80% → 🏅 **Sertifikat A0** |

---

## 6. A1 — المبتدئ · 40 dars

**Chiqish natijasi:** oddiy gap · 2 ta zamon · o'zini tanishtiradi · 800 so'z · Saudiyada oddiy vaziyat.

### Blok 1 · Ot va gap (1–8)

| # | "Nima qila olaman" | Grammatika | 🇸🇦 |
|---|---|---|---|
| 1 | Oddiy tasdiq gap tuzaman | Ismli gap: مُبْتَدَأ + خَبَر | |
| 2 | Kim haqida gapirayotganimni aytaman | Kishilik olmoshlari | |
| 3 | "Bu / anavi" deb ko'rsataman | هذا · هذه · ذلك · تلك | |
| 4 | Aniq/noaniqni farqlayman | ال vs tanvin | |
| 5 | Erkak/ayol so'zni ajrataman | Muzakkar / muannas (ة) | |
| 6 | Narsani tasvirlayman | Sifat va moslashuv (النَّعْت) | |
| 7 | Savol beraman | ما · مَن · أين · كيف · هل · أ | |
| 8 | **Salomlashaman, tanishaman** | Amaliy | ✅ |

### Blok 2 · O'tgan zamon الماضي (9–16)

| # | "Nima qila olaman" | Grammatika |
|---|---|---|
| 9 | "U yozdi / u (ayol) yozdi" | هو / هي — كَتَبَ / كَتَبَتْ |
| 10 | "Sen yozding" | أنتَ / أنتِ — كَتَبْتَ / كَتَبْتِ |
| 11 | "Men yozdim / biz yozdik" | أنا / نحن — كَتَبْتُ / كَتَبْنا |
| 12 | Ko'plikda gapiraman | هم / هنّ / أنتم — كَتَبوا |
| 13 | **Ma'zi to'liq jadval** | 14 shakl + intensiv drill |
| 14 | Kim nima qilganini aytaman | Fe'lli gap: فِعْل + فاعِل + مَفْعول |
| 15 | "Qilmadim" | Inkor: ما + ma'zi |
| 16 | **Bir o'zakdan 5 so'z yasayman** | 🔥 فَعَلَ → فاعِل → مَفْعول → مَفْعَل |

### Blok 3 · Hozirgi zamon المضارع (17–24)

| # | "Nima qila olaman" | Grammatika |
|---|---|---|
| 17 | Prefikslarni bilaman | أ ت ي ن — "ATIN" qoidasi |
| 18 | "U yozadi" | يَكْتُبُ / تَكْتُبُ |
| 19 | "Sen yozasan" | أنتَ / أنتِ |
| 20 | "Men yozaman" | أنا / نحن |
| 21 | **Muzori' to'liq jadval** | 14 shakl + drill |
| 22 | "Qilmayapman" | Inkor: لا + muzori' |
| 23 | Kelasi zamon | سَـ / سَوْفَ |
| 24 | **Ma'zi vs Muzori'** | Aralash solishtirma drill |

### Blok 4 · Ot tizimi (25–32)

| # | "Nima qila olaman" | Grammatika |
|---|---|---|
| 25 | Ikkita narsa haqida | Ikkilik son (المُثَنّى): كِتابان |
| 26 | Ko'plik yasayman | Sog'lom ko'plik: مُعَلِّمون / مُعَلِّمات |
| 27 | Notekis ko'plikni tanib olaman | Singan ko'plik — asosiy vaznlar |
| 28 | "Kimningdir kitobi" | **Idafa (الإضافة)** |
| 29 | "Mening kitobim" | Ulangan olmoshlar: كِتابي · كِتابُكَ |
| 30 | Joyni ko'rsataman | في · على · من · إلى · مع · عن · بـ · لـ |
| 31 | So'z oxiridagi harakatni tushunaman | **I'rob:** رَفْع / نَصْب / جَرّ |
| 32 | Turli inkorni bilaman | لَيْسَ · ما · لا · لَمْ · لَنْ |

### Blok 5 · Kundalik hayot + Saudiya (33–40)

| # | "Nima qila olaman" | Mavzu | 🇸🇦 |
|---|---|---|---|
| 33 | Oilam haqida gapiraman | Oila, qarindoshlar | |
| 34 | 1–10 sanayman | Sonlar + **qutbiylik kirish** | |
| 35 | Narx va yoshni aytaman | Sonlar 11–100 | ✅ |
| 36 | Vaqtni aytaman | Soat, kun, oy, **namoz vaqtlari** | |
| 37 | **Ovqat buyurtma qilaman** | Restoran | ✅ |
| 38 | **Yo'l so'rayman** | Yo'nalish, transport | ✅ |
| 39 | Takrorlash | O'zak/vazn ustaxonasi | |
| 40 | **A1 IMTIHONI** | 4 ko'nikma | 🏅 **Sertifikat A1** |

---

## 7. A2 — ما قبل المتوسط · 45 dars

**Chiqish natijasi:** Saudiyada **mustaqil harakatlanadi** · fe'l boblari · 2000 so'z · harakatsiz oddiy matn.

### 🔥 Blok 1 · FE'L BOBLARI الأوزان (1–12) — eng muhim modul

| # | Bob | Ma'no | Namuna | **O'zbekcha ko'prik** |
|---|---|---|---|---|
| 1 | Umumiy ko'rinish | I–X tizimi | — | "Bitta o'zakdan 10 xil ma'no" |
| 2 | **II** فَعَّلَ | kuchaytirish / sababiyat | عَلَّمَ (o'rgatdi) | **muallim · ta'lim · mudarris** |
| 3 | **III** فاعَلَ | o'zaro harakat | شاهَدَ (ko'rdi) | **mushohada** |
| 4 | **IV** أَفْعَلَ | sababiyat | أَسْلَمَ | **islom · muslim · e'lon** |
| 5 | **V** تَفَعَّلَ | II ning qaytimi | تَعَلَّمَ (o'rgandi) | **tashakkur · tafakkur** |
| 6 | **VI** تَفاعَلَ | o'zaro | تَعاوَنَ | **taovun** |
| 7 | **VII** اِنْفَعَلَ | majhul / qaytim | اِنْكَسَرَ (sindi) | **inqilob** |
| 8 | **VIII** اِفْتَعَلَ | qaytim | اِجْتَمَعَ (yig'ildi) | **ijtimoiy · ehtirom · intizor** |
| 9 | **X** اِسْتَفْعَلَ | **talab qilish** | اِسْتَغْفَرَ | **istiqlol · mustaqbal · istig'for** |
| 10 | **Masdar** | Har bob uchun masdar vazni | تَفْعيل · إِفْعال · اِسْتِفْعال | ta'lim · islom · istiqlol |
| 11 | **Ism fo'il / maf'ul** | Bajaruvchi / bajarilgan | مُعَلِّم / مُعَلَّم | muallim · muslim · mustaqbal |
| 12 | **🔬 BOB USTAXONASI** | Bitta o'zakdan 12 so'z | ع-ل-م | Interaktiv — **wow moment** |

> **12-dars = mahsulotning cho'qqisi.** O'rganuvchi ع-ل-م o'zagidan yasaydi:
> عِلْم · عالِم · عَلَّمَ · مُعَلِّم · تَعْليم · تَعَلَّمَ · مُتَعَلِّم · أَعْلَمَ · إِعْلام · مَعْلومات · اِسْتَعْلَمَ · عالَم
> **12 ta so'z — va hammasi o'zbek tilida bor.** Bu ekranni maxsus dizayn qiling.

### Blok 2 · Illatli fe'llar (13–18)

| # | Mavzu | Namuna |
|---|---|---|
| 13 | Illatli fe'l nima? Turlari | Umumiy ko'rinish |
| 14 | **مِثال** (boshi و/ي) | وَصَلَ · وَجَدَ |
| 15 | **أَجْوَف** (o'rtasi و/ي) | قالَ · كانَ · زارَ |
| 16 | **ناقِص** (oxiri و/ي) | مَشى · دَعا · بَنى |
| 17 | **مُضاعَف + مَهْموز** | مَرَّ · رَدَّ / سَأَلَ · قَرَأَ |
| 18 | Aralash drill | — |

### Blok 3 · Grammatika kengaytirish (19–26)

| # | "Nima qila olaman" | Grammatika |
|---|---|---|
| 19 | "Edi / bo'ldi" | كانَ va opa-singillari |
| 20 | Ta'kid bilan gapiraman | إنَّ va opa-singillari |
| 21 | Buyruq beraman | Amr (الأمر): اُكْتُبْ! |
| 22 | "Yozildi" deyman | Majhul nisbat — kirish |
| 23 | Solishtiraman | أَفْعَل مِن / الأَفْعَل |
| 24 | **Katta sonlarni aytaman** | 100–1000 + **to'liq qutbiylik qoidasi** |
| 25 | Tartibni aytaman | الأوّل · الثاني · الثالث |
| 26 | Vaqt/joyni aniqlayman | Zarf (ظرف الزمان والمكان) |

### 🇸🇦 Blok 4 · SAUDIYA MODULI (27–38) — amaliy yadro

| # | Vaziyat | Tarkib |
|---|---|---|
| 27 | **Aeroport** | Pasport, viza, bojxona |
| 28 | **Transport** | Taksi, Haramayn poyezdi, avtobus |
| 29 | **Mehmonxona** | Bron, check-in, muammo |
| 30 | **Restoran** | Buyurtma, halol, hisob |
| 31 | **Xarid** | Bozor, savdolashish, narx |
| 32 | **Dorixona / shifokor** | Og'riq, dori, favqulodda |
| 33 | **Bank / to'lov** | Valyuta, karta, mada |
| 34 | **🕋 Umra lug'ati** | إحرام · طواف · سعي · تلبية |
| 35 | **🕌 Masjid odobi** | Namoz vaqti, azon, iqoma, safar namozi |
| 36 | **Makka va Madina** | Joylar, yo'nalish, belgilar |
| 37 | **Favqulodda holat** | Politsiya, kasalxona, yo'qotish |
| 38 | **🇸🇦 Hijoziy ustaxonasi** | Eng kerakli **100 ibora** — intensiv SRS |

Har bir dars: MSA + Hijoziy + **AI bilan rol o'yini**.

### Blok 5 · Ko'nikma va imtihon (39–45)

| # | Mavzu |
|---|---|
| 39 | O'qish: belgi, menyu, e'lon (real fotosuratlar) |
| 40 | O'qish: qisqa hikoya — **harakat kamayadi** |
| 41 | Tinglash: real suhbat (sekin → normal) |
| 42 | Yozish: xabar, qisqa xat, tavsif |
| 43 | Gapirish: AI bilan rol o'yini (10 vaziyat) |
| 44 | Umumiy takrorlash |
| 45 | **A2 IMTIHONI** → 🏅 **Sertifikat A2** |

---

## 8. B1 — المتوسط · 50 dars

**Chiqish natijasi:** murakkab gap · fikr bildirish · yangilik o'qish · Qur'on/hadis tuzilmasi · 3800 so'z.

### Blok 1 · Murakkab grammatika (1–14)

| # | Mavzu |
|---|---|
| 1 | Majhul nisbat — to'liq (har bob uchun) |
| 2 | Nisbiy olmoshlar: الذي · التي · الذين · اللاتي |
| 3 | Sifatlovchi gap (noaniq ot bilan) |
| 4 | Shart gap 1: إذا (real) |
| 5 | Shart gap 2: إنْ · مَنْ · ما |
| 6 | Shart gap 3: لَوْ (noreal) |
| 7 | Hol (الحال) |
| 8 | Tamyiz (التمييز) |
| 9 | Istisno: إلّا · غير · سوى |
| 10 | Maf'ul mutlaq (ta'kid) |
| 11 | Maf'ul li-ajlih (sabab) |
| 12 | Muzori' mansub: أنْ · لَنْ · كَيْ · حتّى |
| 13 | Muzori' majzum: لَمْ · لا الناهية |
| 14 | **To'liq i'rob ustaxonasi** |

### Blok 2 · Lug'at (15–26)

15. **Singan ko'pliklar — tizimli** (asosiy 20 vazn) · 16. Ish/kasb · 17. Ta'lim · 18. Salomatlik · 19. Biznes · 20. Texnologiya · 21. OAV · 22. Iqtisod · 23. Sayohat (kengaytirilgan) · 24. Tabiat · 25. Sport · 26. Hissiyot

### 📖 Blok 3 · QUR'ON VA HADIS MODULI (27–34)

> O'zbek auditoriyasi uchun **eng qimmatli modul**. Bu bozorda deyarli hech kim uni to'g'ri qilmagan.

| # | Mavzu |
|---|---|
| 27 | Qur'on tili: MSA'dan farqi |
| 28 | **Eng ko'p uchraydigan 100 Qur'oniy so'z** (matnning ~40% i) |
| 29 | Qisqa suralar tahlili 1 — so'zma-so'z, o'zak bilan |
| 30 | Qisqa suralar tahlili 2 |
| 31 | Hadis matni: tuzilishi (isnod + matn) |
| 32 | Arba'in an-Nawawiy'dan namunalar |
| 33 | Duo va zikr matnlari — grammatik tahlil |
| 34 | Diniy atamalar lug'ati |

### Blok 4 · Ko'nikmalar (35–46)

- **35–38** O'qish: yangilik maqolasi (soddalashtirilgan → original)
- **39–41** Tinglash: podkast, intervyu, xabar
- **42–44** Yozish: rasmiy xat, insho, xulosa
- **45–46** Gapirish: taqdimot, fikr bildirish, munozara (AI bilan)

### Blok 5 · Imtihon (47–50)

47. Takrorlash: grammatika · 48. Takrorlash: lug'at + o'zak · 49. Sinov imtihoni · 50. **B1 IMTIHONI** → 🏅 **Sertifikat B1**

---

## 9. B2 — 2-BOSQICH

⚠️ **B2 ni birinchi versiyada VA'DA QILMANG.** Jahon standarti: **700+ soat**. Ilova ichida bera olmaysiz — real kitob, real suhbat, real muhit kerak.

**To'g'ri pozitsiya: "Davomiy amaliyot rejimi" (Practice Mode)** — dars emas, kunlik oqim:

- Har kuni: 1 yangilik maqolasi + AI tahlil
- Har kuni: 1 podkast parchasi + tushunish savoli
- Haftada: 1 insho → AI baholaydi
- Haftada: 2 ta AI bilan ovozli munozara
- SRS: 3800 → 6000 so'z

**Bu obuna mahsuloti sifatida ancha yaxshi ishlaydi — chunki tugamaydi.**

---

## 10. DARS JSON SCHEMA

Fayl: `content/modules/{level}/{lesson_id}.json`

```json
{
  "id": "a2-09",
  "level": "A2",
  "module": "verb-forms",
  "order": 9,
  "title_uz": "X bob: talab qilish (istiqlol, mustaqbal)",
  "title_ar": "الوزن العاشر: اِسْتَفْعَلَ",
  "can_do_uz": "'So'ramoq / talab qilmoq' ma'nosidagi fe'llarni yasay va tanib olaman",
  "duration_min": 30,
  "prerequisites": ["a2-08"],
  "harakat_level": "new_words_only",

  "hook_uz": "Siz 'istiqlol' va 'mustaqbal' so'zlarini bilasiz. Ular X bobdan yasalgan.",

  "grammar": {
    "point_ar": "اِسْتَفْعَلَ / يَسْتَفْعِلُ / اِسْتِفْعال",
    "explanation_uz": "X bob اِسْتَـ prefiksi bilan yasaladi, ko'pincha 'talab qilmoq' ma'nosini beradi.",
    "table": [
      {"ar": "غَفَرَ", "uz": "kechirdi", "form": "I"},
      {"ar": "اِسْتَغْفَرَ", "uz": "kechirim SO'RADI", "form": "X"},
      {"ar": "اِسْتِغْفار", "uz": "istig'for", "form": "X masdar"}
    ],
    "common_mistakes_uz": [
      "اِسْتَـ dagi hamzani unutish",
      "Muzori'da اِ tushib qolishini bilmaslik: يَسْتَغْفِرُ"
    ]
  },

  "roots": [{
    "root": "ق ب ل",
    "meaning_uz": "qabul qilmoq",
    "uz_cognates": ["qabul", "qibla", "muqobil", "istiqbol", "mustaqbal"],
    "derived": [
      {"ar": "قَبِلَ", "uz": "qabul qildi", "pattern": "فَعِلَ"},
      {"ar": "اِسْتَقْبَلَ", "uz": "kutib oldi", "pattern": "اِسْتَفْعَلَ"},
      {"ar": "اِسْتِقْبال", "uz": "istiqbol", "pattern": "اِسْتِفْعال"},
      {"ar": "مُسْتَقْبَل", "uz": "MUSTAQBAL (kelajak)", "pattern": "مُسْتَفْعَل"}
    ]
  }],

  "vocabulary": [{
    "ar": "اِسْتَخْدَمَ",
    "translit": "istakhdama",
    "uz": "ishlatdi, foydalandi",
    "root": "خ د م",
    "pattern": "اِسْتَفْعَلَ",
    "pos": "verb",
    "audio": "audio/a2/istakhdama.mp3",
    "example_ar": "أَسْتَخْدِمُ الهاتِفَ كُلَّ يَوْمٍ.",
    "example_uz": "Men telefonni har kuni ishlataman.",
    "srs": true
  }],

  "hejazi": [],

  "skills": {
    "reading":   {"text_ar": "...", "questions": [{"q_uz": "...", "a": "..."}]},
    "listening": {"audio": "...", "transcript_ar": "...", "questions": []},
    "speaking":  {"task_uz": "3 gapni ovoz chiqarib o'qing", "target_ar": [], "eval": "azure_pronunciation"},
    "writing":   {"task_uz": "X bobdagi 3 fe'l bilan gap tuzing", "eval": "ai_grammar"}
  },

  "micro_test": [
    {"type": "mcq", "q_uz": "«مُسْتَقْبَل» qaysi bobdan?",
     "options": ["II", "VIII", "X", "IV"], "answer": 2,
     "explain_uz": "مُسْتَـ prefiksi — X bobning ism shakli. O'zbekchada: mustaqbal."},
    {"type": "fill_blank", "q_ar": "أنا ___ الهاتف.", "answer": "أَسْتَخْدِمُ"},
    {"type": "translate_uz_ar", "q_uz": "U kechirim so'radi", "answer": "اِسْتَغْفَرَ"},
    {"type": "dictation", "audio": "...", "answer": "اِسْتِقْبال"},
    {"type": "build_word", "root": "خ د م", "pattern": "اِسْتَفْعَلَ", "answer": "اِسْتَخْدَمَ"}
  ],

  "srs_cards": [
    {"type": "word",    "front": "اِسْتَخْدَمَ", "back": "ishlatdi"},
    {"type": "root",    "front": "ق ب ل", "back": "qabul → qabul, qibla, istiqbol, mustaqbal"},
    {"type": "pattern", "front": "اِسْتَفْعَلَ", "back": "X bob — talab qilmoq"}
  ]
}
```

---

## 11. MIKRO-TEST TIZIMI

### Har dars oxirida — 5–7 savol

| Tur | Tavsif |
|---|---|
| `mcq` | Ko'p tanlovli |
| `fill_blank` | Bo'sh joyni to'ldirish |
| `translate_uz_ar` / `translate_ar_uz` | Tarjima |
| `harakat` | To'g'ri harakat qo'yish |
| `dictation` | Tinglab yozish |
| `match_root` | So'zning o'zagini topish |
| `build_word` | 🔥 O'zak + vazn → so'z yasash |
| `shadowing` | Ovozli takrorlash → AI baho |
| `order_words` | So'zlarni to'g'ri tartibga solish |

**O'tish:** 60%. Past bo'lsa → dars qayta **taklif** qilinadi (majburlanmaydi).

### Har 5 darsda — nazorat testi
15 savol · o'tish **70%** · past bo'lsa xato so'zlar SRS'ga qaytadi.

### Xatolar avtomatik SRS'ga
Har noto'g'ri javob → o'sha so'z/qoida SRS intervalini **qayta boshlaydi**.

---

## 12. IMTIHON VA SERTIFIKAT

### 12.1 Imtihon tuzilmasi

| Bo'lim | Vazn | Savol | Format |
|---|---|---|---|
| 📖 O'qish | 25% | 15 | Matn + tushunish savollari |
| 🎧 Tinglash | 25% | 15 | Audio + savollar |
| ✍️ Yozish | 25% | 3 topshiriq | AI baholaydi |
| 🗣 Gapirish | 25% | 5 topshiriq | Ovozli xabar → AI baholaydi |

**Vaqt:** A0 — 30 daq · A1 — 45 daq · A2 — 60 daq · B1 — 90 daq

### 12.2 Qoidalar

- Savollar **tasodifiy** (savol bazasi kerakli miqdordan **3× katta** bo'lsin)
- **Vaqt cheklangan** (timer)
- Yiqilsa: **24 soatdan keyin** qayta topshirish, yangi savollar bilan

### 12.3 Sertifikat

**Shart:** umumiy **≥ 80%** VA har bir bo'limda **≥ 60%**
*(Gapirishdan 0 olib, o'qishdan 100 olib o'tib ketmasin.)*

```
🏅 ARABIY
شهادة إتمام المستوى

Ism:        {first_name} {last_name}
Daraja:     A2 — ما قبل المتوسط
Ball:       87 / 100
            O'qish 22/25 · Tinglash 21/25 · Yozish 23/25 · Gapirish 21/25
Sana:       13.07.2026
ID:         ARB-A2-7F3K9M
Tekshirish: arabiy.digitalcfo.uz/verify/7F3K9M
[QR kod]
```

**Texnik:**
- **PDF** (reportlab) + **PNG** (Telegram'da ulashish uchun)
- `data/certificates/{cert_id}.pdf`
- `GET /api/verify/{cert_id}` → JSON (ism, daraja, sana, ball)
- Telegram'da: hujjat + rasm + **"Do'stlarga ulashish"** tugmasi
- Dizayn: oltin + to'q yashil, arabcha kalligrafik ramka. Digital CFO brend ranglaridan **farq qilsin**.

---

## 13. KONTENT GENERATSIYA PROMPTI

`backend/services/ai.py` ga:

```
SEN: Arab tili metodisti. O'zbek tilida so'zlashuvchilar uchun dars yaratasan.

KONTEKST:
- O'quvchi: o'zbek tilida so'zlashuvchi, {level} darajada
- Maqsad: Saudiya safari + rasmiy arab tili (فصحى)
- Bu {lesson_number}-dars, mavzu: {topic}
- Allaqachon o'rganilgan: {previous_grammar}
- Hali BILMAYDI: {not_yet_taught}

QAT'IY QOIDALAR:
1. Faqat o'quvchi bilgan grammatikani ishlat. Kelajakdagi mavzuni ISHLATMA.
2. harakat_level={harakat_level} ga mos harakat qo'y.
3. Har bir yangi so'zning O'ZAGINI ko'rsat.
4. So'zning o'zbekcha o'zlashma varianti bo'lsa — MAJBURIY ko'rsat.
5. Tushuntirish tili: o'zbek (lotin). Arabcha faqat misollarda.
6. Grammatikani "qoida" emas, "nima qila olaman" sifatida ber.
7. Diniy kontentda aniq va hurmatli bo'l. Oyat keltirilsa — sura va oyat raqami.

CHIQISH: faqat JSON, schema bo'yicha. Markdown backtick QO'SHMA, preambula YOZMA.

SCHEMA: {lesson_json_schema}
TOPSHIRIQ: {lesson_spec}
```

### ⚠️ Sifat nazorati — majburiy

- **Avtomatik:** barcha arabcha so'zlar lug'at bazasida bormi? Harakat qo'yilganmi? O'zak to'g'rimi?
- **Inson:** har bir darsni chiqarishdan oldin **arab tili o'qituvchisi** ko'rsin.

> AI arab morfologiyasida (ayniqsa illatli fe'llar va singan ko'pliklarda) xato qiladi. Bu — mahsulotingizning **eng katta sifat xavfi**. Bitta noto'g'ri harakat butun ishonchni yo'q qiladi.

---

## 14. TEXNIK IMPLEMENTATSIYA

```
backend/
├── services/
│   ├── content.py      → dars yuklash, prerequisite tekshiruv
│   ├── srs.py          → 4 kartochka turi (word/root/pattern/phrase)
│   ├── ai.py           → kontent generatsiya + yozish/gapirish baholash
│   ├── achievements.py → sertifikat trigger
│   ├── exam.py         🆕 imtihon logikasi, savol tanlash, baholash
│   ├── certificate.py  🆕 PDF/PNG generatsiya + verify
│   └── roots.py        🆕 Root Lab, vazn daraxti
├── db/models.py        → yangi jadvallar (quyida)
└── api/verify.py       🆕 GET /api/verify/{cert_id}

content/
├── curriculum.json     🆕 160 darsning meta-ma'lumoti
├── modules/{a0,a1,a2,b1}/
├── roots.json          🆕 o'zak bazasi + o'zbekcha ko'prik
├── patterns.json       🆕 vazn bazasi
├── hejazi.json         🆕 Hijoziy iboralar
└── exams/{a0,a1,a2,b1}_pool.json  🆕 savol bazasi (3× miqdor)

webapp/src/
├── RootLab.tsx         🆕 o'zak ustaxonasi (wow-funksiya)
├── Exam.tsx            🆕 imtihon UI + timer
└── Certificate.tsx     🆕 sertifikat ko'rish/ulashish
```

**Yangi DB jadvallari:**

```sql
exam_attempts (id, user_id, level, started_at, finished_at,
               score_reading, score_listening, score_writing, score_speaking,
               total_score, passed)

certificates  (id, cert_id, user_id, level, score, issued_at, pdf_path, revoked)

root_progress (id, user_id, root, seen_count, mastered, last_seen)
```

**Audio:** Azure TTS — `ar-SA-HamedNeural` (erkak), `ar-SA-ZariyahNeural` (ayol). Saudiya lahjasiga eng yaqini.

**Talaffuz baholash:** Azure **Pronunciation Assessment API** arab tilini qo'llab-quvvatlaydi. AI transkripsiyadan ancha aniqroq — buni jiddiy ko'rib chiqing.

---

## 15. ISHLAB CHIQISH TARTIBI

Hammasini birdan qilmang.

| # | Nima | Nega bu tartibda |
|---|---|---|
| **1** | `roots.json` + `patterns.json` + **Root Lab** | Farqlovchi xususiyat. U bo'lmasa — oddiy flashcard ilova. |
| **2** | **A0 to'liq** + imtihon + sertifikat | To'liq sikl (dars → test → imtihon → sertifikat) ishlashini isbotlang |
| **3** | **Fikr-mulohaza yig'ing** (50–100 foydalanuvchi) | A1 ni yozishdan **oldin** |
| **4** | **A1** (40 dars) | Fe'l modullari — eng katta xavf, erta sinang |
| **5** | 🇸🇦 **Saudiya moduli** (A2 27–38) — A2 ning qolganidan **oldin** | Bu asosiy sotuv nuqtangiz |
| **6** | A2 ning qolgani (boblar moduli) | |
| **7** | B1 | |
| **8** | B2 = Practice Mode (obuna) | |

> **💡 Alohida mahsulot g'oyasi:**
> **"🕋 Umra uchun 30 kunlik arab tili"** — A2 Saudiya modulidan (27–38) alohida mini-kurs.
> Aniq ehtiyoj · aniq muddat · aniq narx. Asosiy kursga eng yaxshi kirish eshigi.

---

## 16. ESKI REJADAN NIMA O'ZGARDI

| Eski xato | Yangi yechim |
|---|---|
| Qaysi arab tili — aytilmagan | **MSA umurtqa + Hijoziy qatlam** — ochiq qaror |
| Ko'nikmalar bloklarga ajratilgan (28 dars → 3 listening) | **Har darsda 4 ko'nikma** |
| "Verb forms" = **1 dars** | **Fe'llar = 42 dars (26%)** |
| O'zak–vazn tizimi **yo'q** | **Dasturning yadrosi** — o'zbekcha ko'prik bilan |
| Hozirgi zamon oldin, o'tgan keyin | **O'tgan zamon birinchi** |
| Alifbo = **6 dars** | **A0 = 25 dars** (3 ta talaffuz ustaxonasi bilan) |
| I'rob · tasniya · singan ko'plik · sonlar qutbiyligi — **yo'q** | Hammasi qo'shildi |
| 150 darsda **B2 va'da** | **160 darsda halol A2/B1** |
| Harakatdan voz kechish rejasi yo'q | **Bosqichma-bosqich fade + tap-to-reveal** |
| Sertifikat yo'q | **Har darajada · 80%+ · QR bilan tekshiriladigan** |
| Saudiya ehtiyoji tarqoq | **12 darslik alohida 🇸🇦 modul** |
| Qur'on/hadis — yo'q | **B1 da 8 darslik modul** |
| B2'da "Law", "International Relations" | O'chirildi — o'zbek bozorida talab yo'q |

**Eski reja: 54/100**
**Yangi dastur (to'g'ri bajarilsa): 88/100**

Qolgan 12 ball faqat **real foydalanuvchi ma'lumoti** bilan olinadi. Hech qanday reja birinchi urinishda mukammal bo'lmaydi. **A0 ni chiqaring → ma'lumot yig'ing → tuzating.**

---

*ARABIY Curriculum Spec v1.0*
