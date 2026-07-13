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
    dev_auth: bool = False
    # Prod'da doimiy disk yo'li (masalan /data/arabiy.db); bo'sh = loyiha ildizi
    db_path: str = ""
    # Admin Telegram ID — faqat shu foydalanuvchi admin buyruqlaridan foydalanadi
    admin_id: int = 0


settings = Settings()
