from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    All config comes from .env file.
    Change values in .env — they automatically apply everywhere.
    """

    # ── Database ──────────────────────────────────────────
    DATABASE_URL: str       # asyncpg — used by FastAPI
    DATABASE_SYNC_URL: str  # psycopg2 — used only by Alembic

    # ── JWT ───────────────────────────────────────────────
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # ── CORS ──────────────────────────────────────────────
    ALLOWED_ORIGINS: str = "http://localhost:5173"

    # ── App ───────────────────────────────────────────────
    APP_ENV: str = "production"
    DEBUG: bool = False
    MINIO_ENDPOINT: str
    MINIO_ACCESS_KEY: str
    MINIO_SECRET_KEY: str
    MINIO_BUCKET: str = "vikasana-faculty"
    MINIO_SECURE: bool = False
    MINIO_PUBLIC_URL: str | None = None  # optional (if you want public file links)
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    @property
    def origins_list(self) -> list[str]:
        """Splits comma-separated ALLOWED_ORIGINS into a list."""
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]


@lru_cache()
def get_settings() -> Settings:
    return Settings()


# Single instance used across the entire app
settings = get_settings()
