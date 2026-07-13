# CURRICULUM v2 — Bosqichma-bosqich qurish rejasi

> Haqiqat manbasi: [docs/ARABIY_CURRICULUM.md](docs/ARABIY_CURRICULUM.md) (Spec v1.0).
> Bu fayl — o'sha spec'ni **muhandislik bosqichlariga** ajratilgan ish rejasi.
> Tartib spec §15 ga asoslanadi, lekin jonli botni buzmaslik uchun texnik poydevor bosqichlari qo'shilgan.

---

## Hozirgi holat vs Maqsad (farq xaritasi)

| Soha | Hozir (v1, jonli) | Spec (v2) |
|---|---|---|
| Kontent | 3 modul / 19 dars, bitta JSON'da hammasi | 160 dars, `modules/{a0,a1,a2,b1}/{id}.json`, boy sxema (grammar/roots/hejazi/skills/micro_test) |
| O'zak–vazn | yo'q | **Yadro**: roots.json, patterns.json, Root Lab, root/pattern SRS kartalari |
| Mashqlar | choice, listen, match, assemble, type | + mcq, fill_blank, translate, harakat, dictation, match_root, **build_word**, order_words, shadowing |
| SRS | 1 tur (word) | 4 tur (word/root/pattern/phrase), MSA va Hijoziy **alohida deck** |
| Ko'nikmalar | mashqlar aralash | Har darsda 4 ko'nikma: o'qish/tinglash/gapirish/yozish + AI baho |
| Imtihon | yo'q (faqat mikro-natija) | Har daraja: 4 bo'limli imtihon, timer, 80%+60% qoida, 24h qayta topshirish |
| Sertifikat | yo'q | PDF+PNG, QR, `/api/verify/{id}`, ulashish tugmasi |
| Hijoziy | yo'q | Funksional darslarda 🇸🇦 blok + 100 ibora deck |
| Harakat | doim to'liq | Daraja bo'yicha fade + **tap-to-reveal** |
| Kirish yo'llari | 1 ta onboarding | 3 yo'l: to'liq A0 / Qur'on o'quvchi (5 dars tekshiruv) / joylashtiruv testi |

Jonli botga ta'sir: **K4 gacha foydalanuvchi hech narsani sezmaydi** (hamma ish parallel qurilib boradi), K4 oxirida yangi kursga to'liq o'tamiz.

---

## K0 — Poydevor: kontent infratuzilmasi v2

**Maqsad:** yangi dars formatini saqlay, tekshira va generatsiya qila oladigan tizim.

Ishlar:
- `content/` yangi tuzilma: `curriculum.json` (160 dars meta: id, daraja, modul, sarlavha, prerequisite, harakat_level), `modules/{a0,a1,a2,b1}/`, `roots.json`, `patterns.json`, `hejazi.json` (skeletlari)
- `backend/services/content.py` v2: per-dars fayllar, yangi sxema, prerequisite tekshiruv; **eski 3 modul bilan parallel ishlaydi** (bayroq orqali)
- Dars JSON sxemasi (spec §10) uchun Pydantic modellari + `scripts/validate_content.py`: sxema, harakat bor-yo'qligi, o'zak-lug'at mosligi, "bilmagan grammatika ishlatilmaganmi" tekshiruvi
- `backend/services/lesson_gen.py` + `scripts/generate_lesson.py`: spec §13 prompti bilan Claude orqali dars generatsiya → avtomatik validatsiya → JSON saqlash (build-vaqt pipeline, runtime emas)
- DB: `root_progress` jadvali; `user_words`ga `card_type` (word/root/pattern/phrase) va `deck` (msa/hejazi) ustunlari (migratsiya `_ensure_columns` orqali)

**Tayyor sanaladi:** bitta test-dars (a0-22 "O'zak tushunchasi") pipeline orqali generatsiya qilinib, validatordan o'tadi.

---

## K1 — Roots + Patterns + 🔬 Root Lab (wow-funksiya)

**Maqsad:** spec §15 №1 — farqlovchi xususiyat. Jonli botga darhol chiqadi (eski kontentni buzmaydi).

Ishlar:
- `roots.json`: birinchi 20 o'zak (spec §3.2 jadvali — o'zbekcha ko'priklar bilan), audio
- `patterns.json`: A1 vaznlari (§3.3) + bob vaznlari (§3.4)
- `backend/services/roots.py` + `GET /api/roots`, `GET /api/roots/{root}`
- `webapp/src/pages/RootLab.tsx`: o'zak tanlash → yasalgan so'zlar **daraxti** → bosilsa audio+ma'no+o'zbekcha ko'prik; skrinshotga chiroyli dizayn (oltin/zumrad, katta arab yozuvi)
- Home REJIMLAR'dagi kartalardan biri → Root Lab (birinchi ishlaydigan rejim)
- SRS: root/pattern kartalar Takror sahifasida (old/orqa formatlari §3.5)
- Root Lab'ni ko'rgan o'zak → `root_progress.seen_count`

**Tayyor sanaladi:** foydalanuvchi Root Lab'da ك-ت-ب ni ochib "kitob-maktab-kotib-maktub-kutubxona"ni ko'radi, o'zak kartalari SRS'ga tushadi. Deploy qilinadi.

---

## K2 — Dars playeri v2 (yangi sxema + 9 mashq turi)

**Maqsad:** spec §2.1 dars anatomiyasini to'liq o'ynay oladigan player.

Ishlar:
- Player v2 oqimi: hook → grammatika (jadval + keng tarqalgan xatolar) → o'zak ko'prigi → lug'at kartalari → 🇸🇦 hejazi blok (bo'lsa) → 4 ko'nikma → mikro-test → natija
- Yangi mashq komponentlari: `mcq`, `fill_blank`, `translate_uz_ar/ar_uz`, `harakat` (harakat qo'yish), `dictation` (tinglab yozish — arab virtual klaviatura bilan), `match_root`, `build_word` 🔥 (o'zak+vazn→so'z), `order_words`, `shadowing` (eshit→takrorla, v1: o'z-o'zini baholash)
- **Tap-to-reveal**: har qanday arabcha so'zga bosilsa harakat+ma'no+o'zak+vazn (global komponent)
- Yozish mashqi → `POST /api/eval/writing` (Claude: grammatik baho + izoh, o'zbekcha)
- Har 5 darsda nazorat testi (15 savol, 70%); xato javob → SRS interval reset (spec §11)
- Gapirish (ovoz yozish + AI talaffuz bahosi) — **D1 qaroriga bog'liq** (quyida), v1'da shadowing self-check

**Tayyor sanaladi:** K0'dagi test-darslar (a0-01, a0-10, a0-22) yangi playerda boshdan-oxir o'ynaladi (preview'da tekshirilgan).

---

## K3 — Imtihon + Sertifikat dvigateli

**Maqsad:** daraja-agnostik imtihon tizimi (spec §12) — A0 kontenti tayyor bo'lishidan oldin dvigatel tayyor tursin.

Ishlar:
- `content/exams/{level}_pool.json` formati + a0 pool (savollar soni 3×)
- `backend/services/exam.py`: tasodifiy tanlash, 4 bo'lim (25%×4), timer, baholash (≥80% umumiy VA ≥60% har bo'lim), 24 soat qayta topshirish qulfi
- `backend/services/certificate.py`: PDF (reportlab) + PNG (Pillow), oltin+to'q yashil dizayn, QR, `data/certificates/`, ID format `ARB-A2-XXXXXX`
- DB: `exam_attempts`, `certificates`
- API: `POST /api/exam/start`, `POST /api/exam/submit`, `GET /api/verify/{cert_id}` (ochiq, authsiz)
- `webapp`: `Exam.tsx` (timer, bo'limlar, progress), `Certificate.tsx` (ko'rish/ulashish)
- Bot: sertifikatni hujjat+rasm sifatida yuboradi, "Do'stlarga ulashish" tugmasi
- Yozish/gapirish bo'limlari AI baho bilan

**Tayyor sanaladi:** test foydalanuvchi A0 imtihonini topshirib, tekshiriladigan (verify link ishlaydigan) sertifikat oladi.

---

## K4 — A0 to'liq (25 dars) + Onboarding v2 + JONLI O'TISH 🚀

**Maqsad:** spec §15 №2 — to'liq sikl: dars → mikro-test → imtihon → sertifikat. Bu bosqich oxirida bot v2 kursga o'tadi.

Ishlar:
- 25 ta A0 darsni pipeline orqali generatsiya (spec §5 jadvali bo'yicha), har biri validatordan o'tadi
- Audio: edge-tts `ar-SA-HamedNeural` (erkak) + `ar-SA-ZariyahNeural` (ayol) — spec aytgan ovozlar edge-tts'da bepul bor
- **Inson tekshiruvi**: har dars uchun review-varaq (Google Sheets/MD eksport) tayyorlayman — arab tili o'qituvchisiga berasiz (D3)
- Onboarding v2 — uch kirish yo'li (spec §1.4): "harf bilmayman"→A0 to'liq · "Qur'on o'qiyman"→5 darslik tez tekshiruv→A1 kutish rejimi · "biroz bilaman"→15 savollik joylashtiruv testi
- AI reja generatorini yangi curriculum'ga moslash (module_order → dars ketma-ketligi)
- **O'tish**: eski 19 dars arxivga, foydalanuvchilar yangi kursni joylashtiruv testi bilan boshlaydi (D2), progress/XP/streak saqlanadi
- Dashboard "KEYINGI DARS" v2 curriculum bilan ishlaydi

**Tayyor sanaladi:** yangi foydalanuvchi A0 ni boshidan sertifikatgacha o'tadi; jonli botda v2 ishlaydi.

---

## K5 — Analitika + fikr-mulohaza vositalari

**Maqsad:** spec §15 №3 — "A1 yozishdan OLDIN 50–100 foydalanuvchidan ma'lumot". Yig'ish sizda, vositalar menda.

Ishlar:
- Admin: voronka statistikasi (`/funnel`): onboarding→1-dars→A0 yakuni→imtihon; har dars bo'yicha tashlab ketish (drop-off) jadvali; imtihon o'tish foizi
- Foydalanuvchi: `/fikr` buyrug'i + ilova ichida "Fikr bildirish" (Profil sahifasida) → adminga forward
- Dars oxirida ixtiyoriy 1-bosishli baho (👍/👎) → admin hisobotida
- Xato hisobotlari: player'da yuz bergan JS xatolarni backend logiga yuborish

**Tayyor sanaladi:** `/funnel` real ma'lumot ko'rsatadi; siz foydalanuvchi yig'ish kampaniyasini boshlaysiz. *(K6 ga o'tish — fikr-mulohaza tahlilidan keyin, lekin xohlasangiz parallel boshlaymiz.)*

---

## K6 — A1 (40 dars) + A1 imtihoni

Spec §6 bo'yicha 5 blok:
- Blok 1 (1–8): ismli gap, olmoshlar, ishora, sifat, savol + 🇸🇦
- Blok 2 (9–16): **ma'zi** — 3 shaxsdan boshlab to'liq 14 shaklgacha, fe'lli gap, inkor, "bir o'zakdan 5 so'z" 🔥
- Blok 3 (17–24): **muzori'** ("ATIN" qoidasi), kelasi zamon, ma'zi-muzori' solishtiruv drilli
- Blok 4 (25–32): tasniya, ko'pliklar (sog'lom+singan), **idafa**, ulangan olmoshlar, predloglar, **i'rob kirish**, inkor tizimi
- Blok 5 (33–40): oila, sonlar+**qutbiylik kirish**, vaqt/namoz vaqtlari, restoran 🇸🇦, yo'l so'rash 🇸🇦, A1 IMTIHONI
- Yangi texnika: **konjugatsiya drill** komponenti (14 shaklli jadval mashqi), fe'l paradigma SRS

---

## K7 — 🇸🇦 Saudiya moduli (A2 №27–38) — A2 qolganidan OLDIN

Spec §15 №5: asosiy sotuv nuqtasi.
- 12 vaziyatli dars: aeroport, transport (Haramayn), mehmonxona, restoran, xarid/savdolashish, dorixona, bank/mada, 🕋 umra lug'ati, 🕌 masjid odobi, Makka-Madina, favqulodda, Hijoziy ustaxonasi (100 ibora)
- `hejazi.json` to'liq deck + Takror sahifasida **deck almashtirgich** (MSA ⇄ 🇸🇦)
- **AI rol o'yini**: Claude bilan matnli dialog-simulyatsiya (taksichi/ofitsiant/politsiya roli), baho va tuzatishlar bilan
- *(Ixtiyoriy mahsulot: "Umra uchun 30 kun" mini-kursi — alohida qaror, D6)*

---

## K8 — A2 qolgani (№1–26, 39–45) + A2 imtihoni

- 🔥 Boblar moduli (1–12): har bob alohida dars + o'zbekcha ko'prik; **№12 BOB USTAXONASI** — ع-ل-م dan 12 so'z, maxsus interaktiv ekran (Root Lab'ning kengaytmasi)
- Illatli fe'llar (13–18), grammatika kengaytirish (19–26, jumladan sonlar qutbiyligi to'liq)
- Ko'nikma darslari (39–44): real fotosuratlardan o'qish, harakat kamayishi boshlanadi
- A2 IMTIHONI + sertifikat

---

## K9 — B1 (50 dars) + B1 imtihoni

- Murakkab grammatika (1–14): majhul to'liq, nisbiy gaplar, shart gaplar (3 tur), hol/tamyiz/istisno, mansub/majzum, i'rob ustaxonasi
- Lug'at bloklari (15–26): singan ko'pliklar tizimli + 11 mavzu
- 📖 **Qur'on va hadis moduli (27–34)**: eng ehtiyotkor kontent — 100 Qur'oniy so'z, sura tahlillari, isnod/matn, Arba'in namunalari; **inson tekshiruvi majburiy**, oyat manbalari aniq
- Ko'nikmalar (35–46): yangilik maqolasi, podkast, insho, munozara
- B1 IMTIHONI + sertifikat

---

## K10 — B2 = Practice Mode (obuna mahsuloti)

- Kunlik oqim: 1 yangilik + AI tahlil, 1 podkast parcha + savol
- Haftalik: insho → AI baho, 2× AI munozara
- SRS 3800→6000
- To'lov mexanizmi (Telegram Stars / mahalliy to'lov) — **D5 qarori**

---

## Qarorlar kutilmoqda (Decision points)

| # | Savol | Qachon kerak | Mening tavsiyam |
|---|---|---|---|
| **D1** | Gapirish bahosi: Azure Speech (Pronunciation Assessment, bepul F0 tier bor, arabchani qo'llaydi) ulaymizmi? | K2 | v1: shadowing self-check; Azure'ni K6 gacha qo'shish |
| **D2** | Jonli o'tishda mavjud foydalanuvchilar yangi kursni joylashtiruv testi bilan qayta boshlaydi (XP/streak saqlanadi) | K4 | Ha — foydalanuvchi hozir kam, sifat sakrashi katta |
| **D3** | Har darsni **arab tili o'qituvchisi** ko'rishi (spec §13 majburiy deydi) — o'qituvchi topish sizda | K4 dan boshlab | Kamida A0+Qur'on modulini odam ko'rsin |
| **D4** | Sertifikatda familiya — Telegram'da yo'q, imtihon boshida so'raymiz | K3 | Ha, ixtiyoriy maydon |
| **D5** | B2 obuna to'lovi qanday qabul qilinadi | K10 | Telegram Stars (eng oson integratsiya) |
| **D6** | "Umra 30 kun" alohida mini-kurs sifatida chiqariladimi | K7 dan keyin | Bozor testi sifatida ha |

**Xarajat eslatmasi:** 160 dars + imtihon poollari generatsiyasi ≈ **$40–80** (bir martalik, Claude API; darslar statik JSON bo'lib repoga tushadi — foydalanuvchi ko'paygani bilan bu xarajat oshmaydi). Runtime AI (yozish bahosi, rol o'yini, onboarding rejasi) — foydalanishga qarab, avvalgidek.

**Sifat xavfi (spec §13 ogohlantirishi):** AI arab morfologiyasida xato qilishi mumkin — shuning uchun validator (avtomatik) + inson tekshiruvi (D3) ikkalasi ham rejada.

---

## Ish tartibi (qisqa)

```
K0 infra → K1 Root Lab (deploy) → K2 player v2 → K3 imtihon/sertifikat
   → K4 A0 + JONLI O'TISH (deploy) → K5 analitika (siz: foydalanuvchilar)
   → K6 A1 → K7 Saudiya → K8 A2 → K9 B1 → K10 B2/obuna
```

Har bosqich oxirida: build + test + commit + push + (kerak bo'lsa) serverda `git pull` buyrug'ini beraman.
