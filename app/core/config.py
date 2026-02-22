from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    All config comes from .env file.
    Change values in .env — they automatically apply everywhere.
    """

    # ── Database ──────────────────────────────────────────
    DATABASE_URL: str
    DATABASE_SYNC_URL: str

    # ── JWT ───────────────────────────────────────────────
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # ── CORS ──────────────────────────────────────────────
    ALLOWED_ORIGINS: str = "http://localhost:5173"

    # ── App ───────────────────────────────────────────────
    APP_ENV: str = "production"
    DEBUG: bool = False

    # ── MinIO ─────────────────────────────────────────────
    MINIO_ENDPOINT: str = "127.0.0.1:9000"
    MINIO_ACCESS_KEY: str = ""
    MINIO_SECRET_KEY: str = ""

    # ✅ Keep old key for backward compatibility
    MINIO_BUCKET: str = "vikasana-faculty"

    # ✅ NEW: separate buckets (this fixes your ValidationError)
    MINIO_BUCKET_FACULTY: str = "vikasana-faculty"
    MINIO_BUCKET_ACTIVITIES: str = "vikasana-activities"

    MINIO_SECURE: bool = False
    MINIO_PUBLIC_BASE: str = ""

    # ── Email (Brevo / Sendinblue) ────────────────────────
    SENDINBLUE_API_KEY: str = ""
    EMAIL_FROM: str = "admin@vikasana.org"
    EMAIL_FROM_NAME: str = "Vikasana Foundation"

    # ── Faculty Activation ────────────────────────────────
    FRONTEND_BASE_URL: str = "http://localhost:5173"
    ACTIVATION_TOKEN_SECRET: str = "secret"
    ACTIVATION_TOKEN_EXPIRE_HOURS: int = 48

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",  # keep strict (optional)
    )

    @property
    def origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()