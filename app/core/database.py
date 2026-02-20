from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings


# ── Async Engine ──────────────────────────────────────────────────────
# Connects to your PostgreSQL on VPS using asyncpg driver
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,   # Set DEBUG=false in .env to stop SQL logs
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,    # Drops stale connections before use
)

# ── Session Factory ───────────────────────────────────────────────────
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


# ── Base class for all models ─────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ── FastAPI Dependency ────────────────────────────────────────────────
# Inject this into any route with: db: AsyncSession = Depends(get_db)
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
