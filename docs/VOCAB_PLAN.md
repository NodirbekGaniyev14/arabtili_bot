# LUG'AT BO'LIMI — 6000 SO'Z (K16) — REJA

Holat: **reja tasdiqlangan (2026-08-03)** — ish boshlandi.

**Tasdiqlangan qarorlar:** kontent **TO'LIQ QO'LDA** yoziladi (API generatsiya emas) ·
har so'zda **misol jumla bor** · **hamma 6000 so'zga audio**, repo tartibi
o'zgarmaydi (public + dist ikki nusxa) · **umra/ziyorat lug'ati hozircha
qo'shilmaydi**.

Maqsad: darajalar kesimida arab tilining **eng muhim 6000 so'zi** — qidiriladigan,
tinglanadigan, o'rganiladigan alohida lug'at bo'limi.

Manba tamoyillari: `docs/ARABIY_CURRICULUM.md` §2.5 (70% chastota + 30% mavzu),
§2.6 (harakat siyosati), o'zak-vazn yadrosi va o'zbekcha o'zlashma ko'prigi.

---

## 1. Hozirgi holat va bo'shliq

Lug'at hozir **darslardan yig'iladi** (`backend/services/reference.py::vocab_entries`) —
mustaqil bazasi yo'q, faqat `Ma'lumotnoma → Lug'at` tabida ko'rinadi.

| Daraja | Kurikulum maqsadi (jamlangan) | Shu darajada bo'lishi kerak | Hozir bor | Yetishmaydi |
|---|---|---|---|---|
| A0 | 150 | 150 | 95 | **55** |
| A1 | 800 | 650 | 321 | **329** |
| A2 | 2000 | 1200 | 428 | **772** |
| B1 | 3800 | 1800 | 324 | **1476** |
| B2 | 6000 | 2200 | 370 | **1830** |
| **Jami** | **6000** | **6000** | **1538** | **4462** |

Jadval `docs/ARABIY_CURRICULUM.md` §2.5 dagi maqsadlarga aynan mos (B2 = 6000 —
shu rejadagi mantiqiy davomi).

**Muhim:** darsdagi 1538 so'z bazaga KO'CHIRILMAYDI — lug'at ularni darsdan o'qiydi
va yangi 4462 tasi bilan birlashtirib ko'rsatadi. Bitta so'z ikki joyda turmaydi.

---

## 2. So'z qanday tanlanadi

1. **Chastota yadrosi (70%)** — zamonaviy yozma va og'zaki arab tilining eng ko'p
   uchraydigan so'zlari, chastota reytingi (`rank` 1…6000) bilan. Eng ko'p uchraydigan
   100 so'z oddiy matnning ~50% ini qoplaydi — shuning uchun ular A0/A1 da.
2. **Mavzu to'ldiruvi (30%)** — Saudiya safari va kundalik hayot uchun zarur, ammo
   chastotasi past so'zlar (aeroport, retsept, shartnoma...).
3. **Daraja** = chastota reytingi bo'yicha bo'lak, ammo dars so'zining darajasi ustun:
   so'z darsda uchragan bo'lsa, uning darajasi darsdan olinadi.
4. **O'zak oilasi** — imkon qadar bir o'zakdan yasalgan so'zlar bir darajaga tushadi
   (`ك ت ب` → kitob, yozuvchi, ofis, kutubxona bir joyda o'rganiladi).

### Mavzular (36 ta)

| Guruh | Mavzular |
|---|---|
| Kundalik | oila · uy va jihoz · ovqat va ichimlik · kiyim · tana va salomatlik · vaqt va sana · ob-havo · rang va shakl · son va o'lchov |
| Harakat | shahar va transport · safar va aeroport · mehmonxona · xarid va bozor · pul va bank · restoran |
| Ijtimoiy | salomlashuv va odob · his-tuyg'u · xarakter · munosabat va do'stlik · marosim va bayram |
| Ta'lim va ish | maktab va universitet · kasblar · ofis va ish · texnologiya va internet · hujjat va rasmiyat |
| Jamiyat | davlat va qonun · yangiliklar va siyosat · iqtisod va savdo · ta'lim tizimi |
| Tabiat | hayvon · o'simlik · geografiya · ekologiya |
| Til yadrosi | harakat fe'llari · sifatlar · bog'lovchi va yuklama · fikr va tafakkur |

Diniy atamalar (ziyorat/umra) — **kiritilmaydi** (qaror §10.4).

---

## 3. Ma'lumot sxemasi

Fayllar: `content/vocab/a0.json … b2.json` (daraja bo'yicha, har biri bir ro'yxat).

```json
{
  "id": "v-1042",
  "rank": 1042,
  "ar": "مَكْتَب",
  "translit": "maktab",
  "uz": "ofis; ish stoli",
  "pos": "ism",
  "root": "ك ت ب",
  "pattern": "مَفْعَل",
  "plural_ar": "مَكَاتِب",
  "theme": "ofis va ish",
  "level": "A2",
  "example_ar": "أَعْمَلُ فِي مَكْتَبٍ صَغِيرٍ.",
  "example_uz": "Kichik ofisda ishlayman.",
  "audio": "vocab/maktab.mp3",
  "note_uz": "O'zbekcha «maktab» BOSHQA ma'no — arabchada «ofis, ish stoli». Maktab = مَدْرَسَة."
}
```

Fe'llarda qo'shimcha: `past_ar` (كَتَبَ), `present_ar` (يَكْتُبُ), `masdar_ar` (كِتَابَة),
`form` (I–X bob).

`note_uz` — ixtiyoriy, ammo **o'zbekcha o'zlashma bo'lgan har so'zda majburiy**
(loyihaning asosiy metodik ko'prigi): to'g'ri mos kelsa «tanish so'z», ma'nosi
siljigan bo'lsa «soxta do'st» ogohlantirishi.

### Validatsiya qoidalari (`scripts/validate_vocab.py`)

| # | Qoida |
|---|---|
| 1 | `ar` takrorlanmasin — daraja ichida ham, darajalar orasida ham, **darsdagi 1538 so'z bilan ham** (harakatsiz-normallashtirilgan solishtiruv) |
| 2 | `ar`, `example_ar`, `plural_ar` — faqat arab yozuvi; lotin/kirill harfi bo'lmasin |
| 3 | Harakat: A0/A1 — har undoshda majburiy; A2 — yangi so'zda; B1/B2 — ikkiyoqlama o'qiladiganlarida (`docs/ARABIY_CURRICULUM.md` §2.6) |
| 4 | `uz` bo'sh bo'lmasin va **kirill harflari bo'lmasin** (`audit_content.py` dagi `CYRILLIC_LOOKALIKES`) |
| 5 | `root` — «ك ت ب» formatida (3–4 harf, bo'shliq bilan); yasalma bo'lmagan so'zlarda bo'sh |
| 6 | `pattern` — ixtiyoriy, erkin matn (`content/patterns.json` dagi 14 vazn hammasini qoplamaydi) |
| 7 | `theme` — §2 dagi 36 mavzudan biri; `pos` — ism/fe'l/sifat/zarf/harf/ibora |
| 8 | `example_ar` shu so'zni (yoki uning o'zagini) o'z ichiga olsin |
| 9 | `audio` — `vocab/<lotin-slug>.mp3`, slug takrorlanmasin, faqat ASCII |
| 10 | `rank` 1…6000 oralig'ida va takrorlanmasin; `id` = `v-<rank>` |
| 11 | Daraja soni jadvalga (§1) ±2% dan ko'p og'masin |

Validator `validate_content.py` va `audit_content.py` zanjiriga qo'shiladi — bitta
buyruq bilan hamma kontent tekshiriladi.

---

## 4. So'zlarni tayyorlash tartibi (qo'lda)

Kontent **qo'lda yoziladi** — B2 darslaridagi kabi. API generatsiya ishlatilmaydi.

1. Ish birligi — **mavzu bloki**: bitta daraja + bitta mavzu, 40–60 so'z.
   Bir o'zak oilasi bir blokda turadi (`ك ت ب` → kitob, yozuvchi, kutubxona, ofis).
2. Har blok yozilgach darrov `scripts/validate_vocab.py` (§3 dagi 11 qoida) —
   takror, harakat, kirill harfi, misol jumla, audio slug'i tekshiriladi.
3. Blok fayldagi ro'yxatga `rank` tartibida qo'shiladi; `rank` chastota o'rnini
   bildiradi (kunlik to'plam shu tartibda beriladi).
4. Har bosqich oxirida to'liq zanjir: validator → `audit_content.py` → `pytest` →
   `build_audio.py` → `npm run build` → commit + push.

Sur'at: bir sessiyada ~300–500 so'z. 4462 so'z ≈ 10–15 sessiya.

---

## 5. Audio

Nomlash: `vocab/<slug>.mp3`. `content/build_audio.py` yangi fayllarni **avtomatik**
topadi (`ar` maydoni + `audio` maydoni bor har qanday JSON), qo'shimcha kod kerak emas.
Ovoz va tezlik K14 dagidek: `ar-SA-HamedNeural`, qisqa so'zlar sekinroq va takrorlab.

Hajm: 4462 so'z × ~12 KB ≈ **54 MB**. Audio repoda **ikki nusxada** saqlanadi
(`webapp/public/audio` + `webapp/dist/audio`), ya'ni **+108 MB** — qaror §10.3:
hozirgi tartib o'zgarmaydi, deploy sxemasiga tegilmaydi.

---

## 6. Backend

| Fayl | Ish |
|---|---|
| `backend/services/vocab.py` (yangi) | `load_vocab()` (lru_cache), darsdagi so'zlar bilan birlashtirish, `search(q, level, theme, pos)`, `themes()`, `daily_set(user, n)`, `stats()` |
| `backend/api/vocab.py` (yangi) | `GET /v2/vocab/search`, `GET /v2/vocab/themes`, `GET /v2/vocab/daily`, `POST /v2/vocab/learn` (SRS ga qo'shish), `GET /v2/vocab/progress` |
| `backend/services/reference.py` | `vocab_entries()` endi lug'at bazasini ham qo'shadi — Ma'lumotnomadagi qidiruv 6000 so'zni topadi |
| `backend/services/srs.py` | `seed_from_vocab(user_id, ids)` — tanlangan so'zlarni `UserWord` ga qo'shadi (`card_type="word"`, `deck="msa"`) |
| `content/build_audio.py` | o'zgarish YO'Q (avtomatik topadi) |

Yangi DB jadvali **kerak emas**: o'rganilgan so'z = `UserWord` yozuvi (unique
`user_id + ar`). Progress = lug'at so'zlari bilan `UserWord` kesishmasi.

---

## 7. Ilova (frontend)

Yangi sahifa `webapp/src/pages/Vocab.tsx` — Bosh sahifadan «📚 Lug'at» tugmasi.

**Ko'rish rejimi**
- Daraja tablari (A0…B2) + har birida progress halqasi (`o'rganilgan / jami`)
- Mavzu kartalari (36 ta): nom, so'z soni, o'zlashtirish foizi
- Qidiruv: o'zbekcha, arabcha, transliteratsiya, o'zak bo'yicha (mavjud
  `reference.normalize()` ishlatiladi — harakatsiz va hamzasiz izlaydi)
- So'z kartasi: bosilsa audio; kengaytirilsa o'zak, vazn, ko'plik, misol jumla,
  o'zbekcha ko'prik izohi, «shu o'zakdan boshqa so'zlar» havolasi (RootLab)

**O'rganish rejimi (flashcard)**
- «Kunlik 20 so'z» — darajaga mos, o'rganilmaganlaridan, chastota tartibida
- Karta: arabcha + audio → ochiladi: ma'no, misol → «Bilaman / Bilmayman»
- «Bilmayman» → SRS ga tushadi (`UserWord`), keyingi kunlarda Takror bo'limida chiqadi
- Sessiya oxirida XP (mavjud XP tizimi bilan bir xil)

**Ma'lumotnoma** — mavjud Lug'at tabi shu bazadan oziqlanadi (alohida UI o'zgarishi yo'q).

---

## 8. Testlar (`tests/test_vocab.py`)

Sxema va takrorlar · daraja sonlari · mavzu qamrovi · audio fayllari mavjudligi ·
qidiruvning harakatsiz/hamzasiz ishlashi · daily to'plam o'rganilganlarni bermasligi ·
SRS ga qo'shish idempotentligi · API javob sxemasi · Ma'lumotnoma 6000 so'zni ko'rishi.

---

## 9. Bosqichlar

| Bosqich | Ish | Natija |
|---|---|---|
| **K16.1** | Sxema + `validate_vocab.py` + `services/vocab.py` + API + testlar (bank bo'sh) | Poydevor, deploy xavfsiz |
| **K16.2** | `Vocab.tsx` sahifasi + o'rganish rejimi — **mavjud 1538 so'z bilan ishlaydi** | Foydalanuvchi darrov foyda ko'radi |
| **K16.3** | A0 (+55) va A1 (+329) — 1134 so'z | Boshlang'ich lug'at to'liq |
| **K16.4** | A2 (+772) — 1200 so'z | O'rta daraja to'liq |
| **K16.5** | B1 (+1476) — 1800 so'z | 3800 so'z chegarasi |
| **K16.6** | B2 (+1830) — 2200 so'z + audio + yakuniy tekshiruv | **6000 so'z tayyor** |

Har bosqich oxirida: `validate_content.py` + `validate_vocab.py` + `audit_content.py` +
`pytest` 0 xato → `build_audio.py` → `npm run build` → commit + push.

---

## 10. Qarorlar (tasdiqlangan 2026-08-03)

| # | Savol | Qaror |
|---|---|---|
| 10.1 | Tayyorlash usuli | **To'liq qo'lda** — API generatsiya yo'q. Sifat birinchi o'rinda; ~10–15 sessiya |
| 10.2 | Misol jumla har so'zda | **Ha** — so'z kontekstsiz esda qolmaydi |
| 10.3 | Audio | **Hamma 6000 so'zga**, repo tartibi o'zgarmaydi (public + dist ikki nusxa, +108 MB) |
| 10.4 | Umra/ziyorat lug'ati | **Hozircha yo'q** — keyinroq alohida qaraladi |

---

## 11. Xavflar

| Xavf | Yechim |
|---|---|
| Qo'lda yozishda charchoq va sifat pasayishi | Kichik bloklar (40–60 so'z), har blokdan keyin validator; blok tugagach commit |
| Takror so'z | Normallashtirilgan solishtiruv (harakatsiz, hamzasiz) darslar bazasi bilan ham |
| Kirill harflari o'zbekcha matnda | Mavjud `CYRILLIC_LOOKALIKES` tekshiruvi validatorda |
| Repo o'sishi (+108 MB) | Qabul qilingan (§10.3); klon sekinlashsa keyinroq `dist/audio` ajratiladi |
| 6000 so'z foydalanuvchini qo'rqitishi | Mavzu to'plamlari + «kunlik 20 so'z» — bir vaqtda faqat kichik bo'lak ko'rinadi |
| Server xotirasi | 6000 so'z JSON ~3,5 MB, `lru_cache` bilan bir marta yuklanadi — muammo emas |
