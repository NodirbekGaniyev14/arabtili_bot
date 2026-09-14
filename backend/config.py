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

    # ── AI ustoz (services/tutor.py) ──
    # Suhbat modeli: Haiku 4.5 — arzon va tez; javob structured output bilan
    tutor_model: str = "claude-haiku-4-5-20251001"
    # Har foydalanuvchiga kunlik javoblar limiti (token xarajatini cheklaydi)
    tutor_daily_turns: int = 40

    # ── Ovoz → matn (services/stt.py). OpenAI-mos endpoint: Groq yoki OpenAI ──
    # Groq: console.groq.com → whisper-large-v3-turbo (arzon, tez)
    # OpenAI: base_url=https://api.openai.com/v1, model=gpt-4o-mini-transcribe
    stt_api_key: str = ""
    stt_base_url: str = "https://api.groq.com/openai/v1"
    stt_model: str = "whisper-large-v3-turbo"


settings = Settings()


def dev_auth_active() -> bool:
    """DEV_AUTH haqiqatan yoqilganmi.

    Ikki shart: (1) DEV_AUTH=1, (2) BOT_TOKEN bo'sh. Ikkinchi shart tufayli
    prod .env'ga DEV_AUTH=1 tasodifan tushib qolsa ham imzo tekshiruvi
    o'chmaydi — token bor joyda har doim haqiqiy Telegram imzosi talab
    qilinadi.
    """
    return bool(settings.dev_auth) and not settings.bot_token.strip()
