# 🕌 ARABIY — Telegram orqali arab tilini o'rgatuvchi bot (Mini App)

> Ish nomi: **Arabiy** (logo: yashil kvadrat ichida **ع**), bot: `@ArabiyTiliBot` (nom band bo'lsa o'zgartiramiz).
> Maskot: **Jamal** 🐪 — shaxsiy arab tili murabbiyi (Hanyu botdagi panda o'rniga tuya).
> Reference: HanyuXitoyBot (9 ta skrinshot tahlil qilindi) — oqim va tuzilishni undan olamiz, dizayn esa to'liq arabcha atmosferada bo'ladi.

---

## 1. Loyihaning mohiyati

O'zbek tilida so'zlashuvchilar uchun arab tilini **0 dan** o'rgatadigan Telegram Mini App:

1. Foydalanuvchi botga kiradi → Mini App ochiladi → **Jamal bilan qisqa suhbat** (maqsad, daraja, vaqt...).
2. Bilim darajasi **mini-test** bilan aniqlanadi.
3. **AI (Claude)** javoblarni tahlil qilib **shaxsiy kunlik reja** tuzadi.
4. Har kuni: darslar → XP → streak → takror (SRS) → reyting. Duolingo uslubidagi gamifikatsiya.

---

## 2. Reference (Hanyu bot) tahlili — nimani olamiz

| Hanyu botda | Bizda (Arabiy) |
|---|---|
| Panda maskot "Pándy" | Tuya maskot **"Jamal"** 🐪 |
| 你好 katta ieroglif welcome | **السَّلامُ عَلَيْكُم** katta arab yozuvi |
| Onboarding: ism → maqsad → HSK daraja → muddat → kuchsiz tomonlar → kunlik vaqt | Xuddi shu oqim + **haqiqiy mini-test** (bilimni o'zi baholagani yetmaydi — tekshiramiz) |
| "Reja tuzilmoqda..." loading | Xuddi shu (AI chaqiruvi vaqtida) |
| Natija: muhr (HSK 2), "oktabr 2026 gacha", chips | Muhr: daraja (masalan **A1**), "yanvar 2027 gacha A1", kuchsiz tomonlar chips |
| Dashboard: streak, kunlik XP maqsad, statistika, KEYINGI DARS kartasi, REJIMLAR | Xuddi shu tuzilish, arabcha bezaklar bilan |
| Navbar: 6 ta (ieroglif ikonkali) | **5 ta**: Asosiy, Darslar, Takror, Reyting, Profil (arab harfli ikonkalar) |
| Qizil (xitoy) rang palitras | **Zumrad yashil + oltin + qum** (arab/sharq palitras) |

---

## 3. Texnologiyalar

| Qatlam | Tanlov | Sabab |
|---|---|---|
| Bot | **Python 3.12 + aiogram 3.x** | Telegram botlar uchun eng mashhur, async, Mini App bilan yaxshi ishlaydi |
| Backend API | **FastAPI** | aiogram bilan bitta processda ishlaydi, tez, Pydantic bilan |
| Mini App (frontend) | **React 18 + Vite + TypeScript + Tailwind CSS** | Tez ishlab chiqish, chiroyli UI, `@telegram-apps/sdk` bilan integratsiya |
| Ma'lumotlar bazasi | **SQLite (dev) → PostgreSQL (prod)** | SQLAlchemy 2 async orqali — almashtirish oson |
| AI | **Claude API — `claude-opus-4-8`** | Placement tahlili va reja generatsiyasi; structured outputs (JSON schema) bilan kafolatlangan format |
| Audio (talaffuz) | **edge-tts** (Microsoft arab ovozlari, bepul) | Kontent tayyorlash vaqtida mp3 generatsiya qilib saqlaymiz |
| Dev tunnel | **cloudflared** yoki ngrok | Mini App faqat HTTPS URLda ishlaydi — lokal testda tunnel kerak |
| Deploy (keyin) | VPS / Railway / Render | 7-bosqichda hal qilamiz |

**Arxitektura:**

```
Telegram ──► aiogram bot (polling/webhook) ──┐
                                             │  bitta Python process
Mini App (React build) ◄── FastAPI ──────────┤
       │                      │              │
       │ REST /api/*          ├── SQLite/Postgres
       └── initData bilan     └── Claude API (reja, tahlil)
           autentifikatsiya
```

---

## 4. Foydalanuvchi oqimi (flow)

```
/start ──► Bot xabari + "🕌 O'rganishni boshlash" (WebApp tugma)
   │
   ▼
Mini App ochiladi
   │
   ├── Yangi foydalanuvchi ──► ONBOARDING (5-bo'lim) ──► AI reja ──► ASOSIY
   │
   └── Mavjud foydalanuvchi ──► to'g'ridan-to'g'ri ASOSIY sahifa
                                     │
        ┌────────────┬───────────────┼───────────────┬────────────┐
        ▼            ▼               ▼               ▼            ▼
     Asosiy       Darslar         Takror          Reyting      Profil
   (dashboard)  (modullar yo'li)  (SRS kartalar)  (liga)     (statistika)
```

Bot alohida: kunlik eslatma ("🔥 Streak o'chib qolmasin!"), streak xabarlari, yutuq xabarlari.

---

## 5. Onboarding — darajani aniqlash (Mini App ichida)

Har bir savol alohida ekran, tepada **progress bar**, Jamal 🐪 chap tomonda savol beradi (reference'dagidek).

**5.1. Salomlashuv ekrani**
- Katta arab yozuvi: **السَّلامُ عَلَيْكُم** (Assalomu alaykum)
- "Salom! Men **Jamal**man. Shaxsiy arab tili murabbiyingiz. Avval qisqa suhbat — darajangiz, maqsadingiz va kuchsiz tomonlaringiz. Keyin sizga aniq reja tuzaman va birinchi darsdan boshlaymiz."
- [Boshlash] tugmasi

**5.2. Anketa savollari** (har biri kartochka-variantlar, arab harfli ikonkalar bilan):

| # | Savol | Variantlar |
|---|---|---|
| 1 | Sizga qanday murojaat qilay? | matn kiritish |
| 2 | Nima uchun o'rganmoqchisiz? | ✈️ Sayohat · 💼 Ish va biznes · 🎓 O'qish (universitet) · 👨‍👩‍👧 Oila va do'stlar · 🌙 Madaniyat |
| 3 | Hozirgi darajangiz? | Noldan boshlayman · Harflarni bilaman · O'qiyman, lekin tushunmayman · Biroz gaplasha olaman |
| 4 | Qaysi darajaga yetmoqchisiz? | Harflarni o'qish · Oddiy matnlarni tushunish · Erkin suhbat · Professional daraja |
| 5 | Qancha muddatda? | 3 oy · 6 oy · 1 yil · Shoshilmayman |
| 6 | Qaysi tomonlarni kuchaytiramiz? (bir nechta) | 📖 O'qish · ✍️ Yozish · 👂 Tinglash · 🗣 Gapirish · 📐 Grammatika · 📚 Lug'at boyligi |
| 7 | Kuniga qancha vaqt? | 10 daqiqa · 20 daqiqa · 30 daqiqa · 1 soat |

**5.3. Mini-test (haqiqiy bilim tekshiruvi)** — Hanyu botdan farqli ustunligimiz:
- 3-savolda "Noldan boshlayman" desa — test o'tkazilmaydi, daraja = A0.
- Aks holda 6–10 ta adaptiv savol: harfni tanish (ب qaysi?), harakat o'qish (بَ qanday o'qiladi?), so'z o'qish, so'z ma'nosi (كِتاب = ?), oddiy jumla tushunish.
- Har javob vaqti va to'g'riligi saqlanadi.

**5.4. "Reja tuzilmoqda..." ekrani**
- Animatsiya (ustunchalar) + "{Ism}, reja tuzilmoqda..." + "نَتِيجَة — natija muhrlanmoqda..."
- Shu payt backend Claude'ga so'rov yuboradi.

**5.5. Natija ekrani**
- 🎉 "{Ism}, rejangiz tayyor!"
- Muhr (stamp) dizaynidagi karta: **عَرَبِيّ / A1** 
- "**yanvar 2027** gacha **A1**" · "Sayohat · kuniga 20 daqiqa · 6 oy"
- KUCHSIZ TOMONLARINGIZ: [O'qish] [Grammatika] chips
- [Birinchi darsni boshlash] tugmasi

---

## 6. AI integratsiyasi (Claude)

**Model:** `claude-opus-4-8` (structured outputs bilan — javob kafolatlangan JSON).
Narx: $5/1M kirish, $25/1M chiqish token — bitta reja generatsiyasi ≈ $0.03–0.05.

**6.1. Reja generatsiyasi** (onboarding oxirida, 1 marta + har oy yangilash):

Kirish: anketa javoblari + mini-test natijalari (JSON).
Chiqish (Pydantic schema orqali majburiy format):

```json
{
  "level": "A0 | A1 | A2 | B1",
  "level_reason": "nima uchun shu daraja (o'zbekcha, 1-2 jumla)",
  "target_level": "A1",
  "target_date": "2027-01-11",
  "daily_xp_goal": 30,
  "daily_minutes": 20,
  "focus_areas": ["reading", "grammar"],
  "module_order": ["alphabet", "greetings", "family", ...],
  "weekly_schedule": [{"day": 1, "tasks": ["yangi dars", "5 ta so'z takror"]}, ...],
  "motivation": "Jamaldan shaxsiy motivatsion xabar (o'zbekcha)"
}
```

Bu reja DBga saqlanadi va: kunlik XP maqsadni, darslar tartibini, "Bugungi maqsad" kartasini boshqaradi.

**6.2. Keyingi bosqichlarda (6–7-bosqich):**
- Xato tahlili: foydalanuvchi ko'p adashgan mavzular bo'yicha AI izohli tushuntirish beradi.
- Haftalik hisobot: "Bu hafta 45 ta so'z o'rgandingiz, zaif joy — harakatlar".
- (Ixtiyoriy) "AI ustoz bilan suhbat" rejimi.

**Xavfsizlik:** `ANTHROPIC_API_KEY` faqat serverda (.env), frontendga hech qachon chiqmaydi.

---

## 7. Dizayn tizimi — "Arab atmosferasi" 🕌

**7.1. Rang palitras** (Hanyu qizilining o'rniga sharqona yashil-oltin):

| Rol | Rang | Kod |
|---|---|---|
| Fon | Qum / krem | `#FAF6EE` |
| Asosiy (primary) | Zumrad yashil | `#0E6B4E` |
| Primary to'q | Chuqur yashil | `#0A4D38` |
| Aksent | Oltin | `#C9A227` |
| Ikkinchi aksent | Terrakota | `#C0603D` (xatolar, olov 🔥) |
| Matn | To'q jigarrang-qora | `#26211A` |
| Kartalar | Oq-krem | `#FFFDF7`, border `#EBE3D2` |

**7.2. Shriftlar:**
- Arabcha matn: **Amiri** (klassik nasx uslubi) — sarlavha/katta harflar uchun; **Noto Naskh Arabic** — mayda matn.
- Lotincha/o'zbekcha: **Manrope** (sarlavha) + **Inter/Nunito Sans** (matn).

**7.3. Atmosfera effektlari (asosiy sahifa):**
- Fonda **katta yarim shaffof arab harflari** suzib turadi (ع م ب ن) — reference'dagi 好 kabi, lekin bir nechta va sekin animatsiyali.
- **Islimiy geometrik naqsh** (8 qirrali yulduz / girih) — juda past opacity'da fon teksturasi sifatida.
- Kartalarda **arka (mehrob) shaklidagi** yumaloq tepalik elementlari.
- Hilol 🌙 va yulduz motivlari streak/yutuqlarda.
- KEYINGI DARS kartasi: yashil gradient + o'ng tomonda katta shaffof arabcha so'z (masalan **سَلام**).
- Har dars boshida harf "yozilish" animatsiyasi (SVG stroke) — arab xattotligi hissi.

**7.4. Navbar (pastki, 5 ta):**

| Ikonka (arab) | Yozuv | Sahifa |
|---|---|---|
| بيت | Asosiy | Dashboard |
| درس | Darslar | Modullar yo'li |
| كرر | Takror | SRS kartalar |
| نجم | Reyting | Liga/leaderboard |
| أنا | Profil | Statistika, sozlamalar |

Aktiv tab — yashil, arab harfi ikonka sifatida (reference'dagi 家学复声我 uslubida).

---

## 8. Sahifalar (Mini App)

**8.1. ASOSIY (dashboard)** — 1-skrinshotga mos:
- Header: `ع Arabiy` logo + 🔥 streak (kun)
- "Xayrli kech, {ism}!" (vaqtga qarab: tong/kun/kech)
- **Bugungi maqsad** kartasi: XP halqa progress (`0/30 XP`), "Bugun 30 XP qoldi"
- Statistika qatori: **so'z** · **dars** · **aniqlik %**
- **KEYINGI DARS · 1/15** kartasi: "Salomlashish" + [Boshlash ›]
- **REJIMLAR**: Alifbo mashqi · Tinglash · Lug'at kartalari · Tez takror

**8.2. DARSLAR** — modullar yo'li (Duolingo path uslubida):
- Modullar vertikal yo'l bo'ylab: tugallangan (oltin), joriy (yashil, pulsatsiya), qulflangan (kulrang)
- Har modul ichida 3–7 dars

**8.3. DARS PLAYER** — mashqlar ketma-ketligi (tepada progress bar, chapda ❤️ yoki oddiy):
Mashq turlari:
1. **Tanlash** — so'z → 4 tarjima varianti (va teskarisi)
2. **Harf/tovush** — audio 🔊 → qaysi harf?
3. **Moslashtirish** — 5 juft (arabcha ↔ o'zbekcha)
4. **Jumla yig'ish** — so'z banki'dan tartib bilan
5. **Tinglash** — audio → nima deyildi?
6. **Yozish** — ekran arab klaviaturasi bilan so'z terish
- Har mashq: to'g'ri = yashil + XP, xato = terrakota + to'g'ri javob ko'rsatiladi
- Dars oxiri: natija ekrani (XP, aniqlik, yangi so'zlar) + konfetti

**8.4. TAKROR (SRS)**:
- "Bugun takrorlash kerak: 12 ta so'z"
- Flashcard: arabcha so'z + 🔊 → ochish → [Bilmadim] [Qiyin] [Bildim] [Oson]
- SM-2 soddalashtirilgan intervallar: 1 → 3 → 7 → 14 → 30 kun

**8.5. REYTING**:
- Haftalik liga (XP bo'yicha): Top-10 jadval, o'z o'rni ajratilgan
- Ligalar: 🥉 Bronza → 🥈 Kumush → 🥇 Oltin → 💎 Zumrad
- Do'stlarni taklif qilish (referal havola)

**8.6. PROFIL**:
- Avatar (Telegram'dan), ism, daraja muhri (A1)
- Umumiy statistika: jami XP, eng uzun streak, o'rganilgan so'zlar, darslar
- Yutuqlar (badges): "Birinchi qadam", "7 kunlik olov", "Alifbo ustasi"...
- Sozlamalar: kunlik maqsad, eslatma vaqti, ovoz

**8.7. ONBOARDING** — 5-bo'limda tavsiflangan.

---

## 9. O'quv kontenti (dastur)

**Modul 0 — Alifbo** (eng muhim, 10–12 dars):
1. Harflar guruhlari: ب ت ث · ج ح خ · د ذ ر ز · س ش ص ض · ط ظ ع غ · ف ق ك ل · م ن هـ و ي · ا ء
2. Harflarning 4 shakli (boshida/o'rtasida/oxirida/alohida)
3. Harakatlar: fatha, kasra, damma · sukun · shadda · tanvin
4. Cho'ziq unlilar (madd): ا و ي
5. O'qish mashqlari (bo'g'in → so'z)

**Boshlang'ich modullar (A1 birinchi qism, har biri 5–7 dars, 1-modul = 15 dars reference kabi):**
1. **Salomlashish** — السلام عليكم، صباح الخير، كيف حالك؟
2. **Tanishish** — ismim, qayerdanman, kasbim
3. **Oila** — أب، أم، أخ، أخت...
4. **Sonlar 1–10**
5. **Ranglar va sifatlar**
6. **Uy va narsalar**
7. **Ovqat va ichimlik**
8. **Kunlik ishlar (fe'llar)**

**Kontent formati** — `content/modules/*.json`:

```json
{
  "id": "greetings",
  "title": "Salomlashish",
  "arabic_title": "التَّحِيَّات",
  "lessons": [{
    "id": "greetings-1",
    "title": "Assalomu alaykum",
    "new_words": [
      {"ar": "السَّلامُ عَلَيْكُم", "translit": "assalāmu 'alaykum", "uz": "Assalomu alaykum", "audio": "salam.mp3"}
    ],
    "exercises": [
      {"type": "choice", "prompt_ar": "السَّلام", "options": ["Salom", "Rahmat", "Xayr", "Ha"], "correct": 0}
    ]
  }]
}
```

Audio: `edge-tts` (arab ovozi, masalan `ar-SA-HamedNeural`) bilan oldindan mp3 generatsiya qilinadi → `webapp/public/audio/`.

---

## 10. Gamifikatsiya

| Element | Qoida |
|---|---|
| XP | Mashq = 2 XP · Dars tugatish = 10 XP · Mukammal dars (xatosiz) = +5 bonus · Takror sessiyasi = 5 XP |
| Kunlik maqsad | AI rejadan (10 daq = 20 XP, 20 daq = 30 XP, 30 daq = 50 XP, 1 soat = 80 XP) |
| Streak 🔥 | Kunlik maqsadning kamida yarmi bajarilsa saqlanadi; bot kechqurun eslatadi |
| Aniqlik | To'g'ri javoblar % (oxirgi 7 kun) |
| Liga | Haftalik XP reytingi, yakshanba kechasi yakunlanadi |
| Yutuqlar | ~15 ta badge (birinchi dars, 7/30/100 kun streak, 100 so'z, alifbo tugatildi...) |

---

## 11. Ma'lumotlar bazasi sxemasi

```
users            (id, tg_id, name, username, created_at, last_active, settings_json)
placements       (id, user_id, answers_json, test_results_json, created_at)
plans            (id, user_id, level, target_level, target_date, daily_xp_goal,
                  focus_areas_json, module_order_json, motivation, created_at)
progress         (id, user_id, lesson_id, status, accuracy, xp_earned, completed_at)
user_words       (id, user_id, word_id, ease, interval_days, due_date, correct_count, wrong_count)
xp_log           (id, user_id, amount, source, created_at)
streaks          (user_id, current, longest, last_activity_date)
achievements     (id, user_id, badge_id, earned_at)
```

(So'zlar va darslar JSON fayllardan o'qiladi — DBda faqat foydalanuvchi progressi.)

---

## 12. API endpointlar (asosiylari)

```
POST /api/auth              — initData validatsiya → sessiya/user
GET  /api/me                — profil + streak + bugungi XP
POST /api/onboarding        — anketa+test javoblari → Claude → reja
GET  /api/plan              — joriy reja
GET  /api/modules           — modullar ro'yxati + progress
GET  /api/lessons/{id}      — dars kontenti
POST /api/lessons/{id}/done — natija, XP, progress yozish
GET  /api/review            — bugungi SRS kartalar
POST /api/review/answer     — SRS javob (interval yangilash)
GET  /api/leaderboard       — haftalik reyting
GET  /api/profile/stats     — profil statistikasi
```

**Xavfsizlik:** har bir so'rovda Telegram `initData` HMAC-SHA256 orqali BOT_TOKEN bilan tekshiriladi (o'zini boshqa qilib ko'rsatish mumkin emas).

---

## 13. Papka tuzilishi

```
arabtili_bot/
├── PLAN.md                  ← shu fayl
├── .env                     ← BOT_TOKEN, ANTHROPIC_API_KEY (gitga kirmaydi)
├── backend/
│   ├── main.py              ← FastAPI + aiogram birga ishga tushadi
│   ├── bot/                 ← handlerlar, eslatmalar
│   ├── api/                 ← routerlar (auth, onboarding, lessons, review...)
│   ├── services/            ← ai.py (Claude), srs.py, xp.py, telegram_auth.py
│   ├── db/                  ← models.py, session.py
│   └── requirements.txt
├── webapp/                  ← React + Vite + TS + Tailwind
│   ├── src/
│   │   ├── pages/           ← Home, Lessons, LessonPlayer, Review, Rating, Profile, Onboarding/
│   │   ├── components/      ← NavBar, XPRing, StreakBadge, ArabicBg, Mascot...
│   │   ├── lib/             ← api.ts, telegram.ts
│   │   └── styles/
│   └── public/audio/
├── content/
│   ├── modules/*.json       ← darslar
│   └── build_audio.py       ← edge-tts bilan mp3 generatsiya
└── scripts/
```

---

## 14. Bosqichma-bosqich reja (roadmap)

### ✅ 0-bosqich — Reja (tayyor: shu hujjat)

### ✅ 1-bosqich — Skelet (poydevor)
- Papka tuzilishi, git, .env namunasi
- FastAPI + aiogram bitta processda ishga tushadi
- React+Vite+Tailwind app, Telegram SDK ulangan
- Bot `/start` → WebApp tugma → Mini App ochiladi ("Salom" sahifa)
- cloudflared tunnel bilan telefonda test
- **Natija:** bot ishlaydi, Mini App ochiladi

### ✅ 2-bosqich — Asosiy sahifa (arab atmosferasi)
- Dizayn tizimi: ranglar, shriftlar (Amiri), fon effektlari (suzuvchi harflar, girih naqsh)
- Dashboard: header, salomlashuv, XP halqa, statistika, KEYINGI DARS kartasi, REJIMLAR
- 5 ta navbar (arab harfli ikonkalar), sahifalar orasida routing
- Hozircha mock (test) ma'lumotlar bilan
- **Natija:** 1-skrinshotdagi kabi, lekin arabcha uslubdagi to'liq dashboard

### ✅ 3-bosqich — Onboarding + AI reja
- Welcome ekrani (Jamal, السلام عليكم)
- 7 ta anketa savoli + adaptiv mini-test (savollar bazasi bilan)
- Backend: `POST /api/onboarding` → Claude (`claude-opus-4-8`, structured output) → reja DBga
- "Reja tuzilmoqda..." animatsiyasi + natija (muhr) ekrani
- initData autentifikatsiya, users/plans jadvallar
- **Natija:** yangi foydalanuvchi to'liq onboardingdan o'tib, AI rejasini oladi

### ✅ 4-bosqich — Darslar
- Kontent: Alifbo moduli (10 dars) + Salomlashish (5 dars), audio generatsiya
- Darslar sahifasi (modullar yo'li)
- Dars player: 6 xil mashq turi, XP hisoblash, natija ekrani
- Progress DBga yoziladi, dashboard real ma'lumot ko'rsatadi
- **Natija:** haqiqiy darslarni o'tish mumkin

### ✅ 5-bosqich — Takror (SRS)
- user_words + SM-2 intervallar
- Takror sahifasi (flashcardlar, 4 tugma)
- Dashboard'da "bugun takrorlash kerak: N ta so'z"
- **Natija:** o'rganilgan so'zlar unutilmaydi

### ✅ 6-bosqich — Gamifikatsiya to'liq
- Streak logikasi + bot eslatmalari (kechqurun push)
- Haftalik liga (reyting sahifasi), yutuqlar (badges)
- AI: xatolar bo'yicha izoh / haftalik hisobot
- **Natija:** qaytib kelish motivatsiyasi ishlaydi

### 🚀 7-bosqich — Profil (✅), sayqal, deploy (jarayonda)
- Profil sahifasi to'liq, sozlamalar
- Animatsiyalar, haptic feedback, loading skeletlari, xato holatlari
- PostgreSQL'ga o'tish, webhook rejimi, VPS/Railway deploy
- **Natija:** ishlab turgan ommaviy bot

---

## 15. Boshlashdan oldin sizdan kerak bo'ladi

1. **BOT_TOKEN** — @BotFather'dan yangi bot yarating (`/newbot`) va tokenni bering.
2. **ANTHROPIC_API_KEY** — console.anthropic.com dan (3-bosqichgacha kerak bo'ladi).
3. Bot nomi/username tanlovi (taklif: "Arabiy — arab tilini bepul o'rganish").

---

*Reja tasdiqlangach 1-bosqichdan boshlaymiz. Har bosqich oxirida ishlaydigan natijani telefonda tekshirib ko'rasiz.*
