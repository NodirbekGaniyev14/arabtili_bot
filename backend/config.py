from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


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
    # K23.4: VIP suhbat va mock uchun kuchliroq model (masalan claude-sonnet-5, ~2× narx).
    # Bo'sh = hamma uchun tutor_model. Kunlik savol/yozuv/onboarding baribir tutor_model.
    tutor_vip_model: str = ""
    # VIP foydalanuvchiga kunlik javoblar limiti (token xarajatini cheklaydi):
    # 30 × ~$0.003 ≈ $0.09/kun — eng faol VIP ham oyiga ~$2.7 dan oshmaydi
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
    # K18.5 avto to'lov — Telegram Payments (services/payments.py). BotFather →
    # /mybots → bot → Payments → Payme yoki Click → provayder kabinetida shartnoma
    # → BotFather bergan token. FAQAT serverdagi .env'da. Bo'sh = faqat chek oqimi.
    pay_provider_token: str = ""
    pay_provider_name: str = "Payme / Click"

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


settings = Settings()


def dev_auth_active() -> bool:
    """DEV_AUTH haqiqatan yoqilganmi.

    Ikki shart: (1) DEV_AUTH=1, (2) BOT_TOKEN bo'sh. Ikkinchi shart tufayli
    prod .env'ga DEV_AUTH=1 tasodifan tushib qolsa ham imzo tekshiruvi
    o'chmaydi — token bor joyda har doim haqiqiy Telegram imzosi talab
    qilinadi.
    """
    return bool(settings.dev_auth) and not settings.bot_token.strip()
