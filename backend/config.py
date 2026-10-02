import logging
from pathlib import Path

from pydantic import ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent

# K28.3: eski avlod → joriy avlod (narxi bir xil: $2/$10). `.env` da eski nom qolib ketsa ham yangisiga
# o'tiladi (server faylini men o'zgartira olmayman) va /tekshir «.env ni yangilang» deb ogohlantiradi.
LEGACY_MODELS = {"claude-sonnet-5": "claude-sonnet-5-5"}
UPGRADED: dict[str, tuple[str, str]] = {}  # ENV nomi → (eski, yangi)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str = ""
    webapp_url: str = ""
    anthropic_api_key: str = ""
    # DIQQAT: faqat lokal ishlab chiqish uchun. Imzo tekshiruvini o'chiradi!
    # Xavfsizlik uchun bu bayroq BOT_TOKEN bo'sh bo'lgandagina amal qiladi
    # (dev_auth_active'ga qarang) — prod'da .env'da qolib ketsa ham ishlamaydi.
    dev_auth: bool = False
    # Prod'da doimiy disk yo'li (masalan /data/arabiy.db); bo'sh = loyiha ildizi
    db_path: str = ""
    # Admin Telegram ID — faqat shu foydalanuvchi admin buyruqlaridan foydalanadi
    admin_id: int = 0
    # Bot username (@siz) — taklif havolasi t.me/<bot>?start=ref<id> uchun
    bot_username: str = "JamalArabiy_bot"

    # ── AI ustoz (services/tutor.py) ──
    # Suhbat modeli: Haiku 4.5 — arzon va tez; javob structured output bilan
    tutor_model: str = "claude-haiku-4-5-20251001"
    # K23.4: VIP suhbat va mock uchun kuchliroq model. K28.3: standart Sonnet 5.5 ($2/$10 — Haiku 4.5 ($1/$5) dan 2× narx).
    # O'chirish: serverdagi .env da `TUTOR_VIP_MODEL=` (bo'sh) → VIP ham tutor_model. Bepul o'quvchilar hamda kunlik
    # savol / yozuv / onboarding / rol o'yini har doim tutor_model (Haiku). `.env` dagi qiymat shu standartdan ustun.
    # Sonnet 5/5.5 `thinking` berilmasa o'zi o'ylaydi — tutor._call max_tokens'ga zaxira qo'shadi (THINKING_HEADROOM).
    tutor_vip_model: str = "claude-sonnet-5-5"
    # K28: qo'lyozma (daftar surati) o'qish — kuchliroq vision modeli; xato bersa tutor_model bilan qayta.
    # Arab qo'lyozmasini Haiku ko'pincha o'qiy olmadi («yozganimni o'qimaydi»). Bo'sh = tutor_model.
    writing_model: str = "claude-sonnet-5-5"
    # VIP foydalanuvchiga kunlik javoblar limiti (token xarajatini cheklaydi):
    # Haiku: 30 × ~$0.003 ≈ $0.09/kun (~$2.7/oy). Sonnet 5.5 da taxminan 1.5–2.5× (eng faol VIP ≈ $4–7/oy) —
    # `/ustoz` da «model bo'yicha» sarfni kuzating; kerak bo'lsa shu limitni tushiring.
    tutor_daily_turns: int = 30
    # VIP'siz kunlik bepul javoblar (tatib ko'rish uchun; 0 = to'liq qulf)
    tutor_free_turns: int = 3

    # ── VIP tarif va to'lov (services/billing.py) ──
    # Qabul qiluvchi karta — FAQAT serverdagi .env'da (git'da yo'q)
    pay_card_number: str = ""
    pay_card_holder: str = ""
    pay_price_month: int = 40_000
    pay_price_3month: int = 100_000
    # Chegirma «eski narx» (avvalgi haqiqiy narxlar) — 0 bo'lsa chegirma/taymer yo'q
    pay_old_price_month: int = 90_000
    pay_old_price_3month: int = 240_000
    # Chegirma taymeri: paywall birinchi ochilganidan boshlab (soat)
    pay_discount_hours: int = 24
    # Savollar uchun Telegram username (@ belgisisiz)
    support_username: str = ""
    # Avto to'lov (Telegram Payments) 2026-09-21 da olib tashlandi — faqat chek oqimi.
    # .env'dagi PAY_PROVIDER_TOKEN e'tiborsiz qoldiriladi (extra="ignore").

    # ── Ovoz → matn (services/stt.py). OpenAI-mos endpoint: Groq yoki OpenAI ──
    # Groq: console.groq.com → whisper-large-v3-turbo (arzon, tez)
    # OpenAI: base_url=https://api.openai.com/v1, model=gpt-4o-mini-transcribe
    # whisper-large-v3 — turbo'dan aniqroq (o'zbek aksentli o'quvchi nutqi, qisqa
    # javoblar); narx $0.111/soat audio — baribir arzon. Server .env'da STT_MODEL
    # eski turbo bo'lsa, o'chiring yoki shu qiymatga o'zgartiring.
    stt_api_key: str = ""
    stt_base_url: str = "https://api.groq.com/openai/v1"
    stt_model: str = "whisper-large-v3"
    # K21.7 OpenAI STT (gpt-4o-transcribe): kalit bo'lsa ovoz AVVAL shu orqali; xato/limitda Groq (yuqoridagi) zaxira
    stt_openai_api_key: str = ""
    stt_openai_model: str = "gpt-4o-transcribe"
    stt_openai_base_url: str = "https://api.openai.com/v1"

    # ── K30 Jonli ovozli suhbat (services/live_voice.py) — Google Gemini Live API ──
    # Kalit: aistudio.google.com → Get API key. Bo'sh = «🎙 Jonli AI bilan suhbat» tugmasi ko'rinmaydi.
    gemini_api_key: str = ""
    live_model: str = "gemini-3.8-live"
    # Ovoz: Gemini TTS ovozlaridan biri (Charon — erkak, tushuntiruvchi; Jamal ustozga mos)
    live_voice: str = "Charon"
    # Bitta suhbat davomiyligi (Gemini ulanishi ~10 daqiqa yashaydi) va jimlikda yopish
    live_max_seconds: int = 540
    live_idle_seconds: int = 60
    # Limitlar (0 = cheklovsiz — egasi qarori 2026-10-01: hozircha cheklamaymiz, sarfni kuzatamiz)
    live_free_seconds_day: int = 0
    live_vip_seconds_month: int = 0
    # Kunlik sarf shundan oshsa adminga bir marta ogohlantirish (limit emas), USD
    live_daily_budget_usd: float = 5.0
    # Sinov/preview: haqiqiy Gemini o'rniga soxta suhbatdosh (kalitsiz UI sinovi)
    live_fake: bool = False

    @field_validator("tutor_vip_model", "writing_model")
    @classmethod
    def _upgrade_legacy_model(cls, v: str, info: ValidationInfo) -> str:
        new = LEGACY_MODELS.get((v or "").strip())
        if not new:
            return v
        UPGRADED[(info.field_name or "").upper()] = (v, new)
        log.warning("%s=%s eski avlod — %s ishlatiladi (narx bir xil); .env ni yangilang", (info.field_name or "").upper(), v, new)
        return new


settings = Settings()


def dev_auth_active() -> bool:
    """DEV_AUTH haqiqatan yoqilganmi.

    Ikki shart: (1) DEV_AUTH=1, (2) BOT_TOKEN bo'sh. Ikkinchi shart tufayli
    prod .env'ga DEV_AUTH=1 tasodifan tushib qolsa ham imzo tekshiruvi
    o'chmaydi — token bor joyda har doim haqiqiy Telegram imzosi talab
    qilinadi.
    """
    return bool(settings.dev_auth) and not settings.bot_token.strip()
