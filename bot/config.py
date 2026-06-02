from pathlib import Path
from typing import List, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    BOT_TOKEN: str = ""
    # Telegram'ga ulanish uchun proxy (Rossiya kabi bloklangan joylarda kerak).
    # Masalan: http://user:pass@host:port  yoki  socks5://host:port
    TELEGRAM_PROXY: str = ""
    # vergul bilan ajratilgan ID lar, masalan "123,456". String sifatida o'qiladi,
    # so'ng property'lar orqali ro'yxatga aylantiriladi.
    SUPERADMIN_IDS: str = ""
    ADMIN_IDS: str = ""

    ABKM_TOKEN: str = ""
    ABKM_BASE_URL: str = "https://abkm.mehnat.uz/api/service_vacancies"

    DEFAULT_YEAR: Optional[int] = None
    DEFAULT_MONTH: Optional[int] = None

    DB_PATH: str = "vacancy.db"
    LOG_LEVEL: str = "INFO"
    TIMEZONE: str = "Asia/Tashkent"

    @field_validator("DEFAULT_YEAR", "DEFAULT_MONTH", mode="before")
    @classmethod
    def _empty_to_none(cls, v):
        if v is None or (isinstance(v, str) and v.strip() == ""):
            return None
        return v

    @staticmethod
    def _parse_ids(raw: str) -> List[int]:
        return [int(x.strip()) for x in raw.split(",") if x.strip()]

    @property
    def superadmin_ids(self) -> List[int]:
        return self._parse_ids(self.SUPERADMIN_IDS)

    @property
    def admin_ids(self) -> List[int]:
        return self._parse_ids(self.ADMIN_IDS)

    @property
    def db_url(self) -> str:
        return f"sqlite+aiosqlite:///{BASE_DIR / self.DB_PATH}"

    @property
    def logs_dir(self) -> Path:
        d = BASE_DIR / "logs"
        d.mkdir(exist_ok=True)
        return d

    def is_superadmin(self, user_id: int) -> bool:
        return user_id in self.superadmin_ids

    def is_admin(self, user_id: int) -> bool:
        """Yordamchi admin (superadmin ham admin huquqlariga ega)."""
        return user_id in self.admin_ids or self.is_superadmin(user_id)


settings = Settings()  # type: ignore[call-arg]
