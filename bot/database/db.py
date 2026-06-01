from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.config import settings
from bot.database.models import Base


engine = create_async_engine(settings.db_url, echo=False, future=True)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _migrate(conn) -> None:
    """Yengil migratsiya: yangi ustunlarni mavjud jadvalga qo'shadi (SQLite)."""
    res = await conn.execute(text("PRAGMA table_info(users)"))
    cols = {row[1] for row in res.fetchall()}
    if "is_active" not in cols:
        await conn.execute(
            text("ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT 1")
        )
        logger.info("Migration: users.is_active ustuni qo'shildi.")


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _migrate(conn)
    logger.info("Database tables ready.")


async def close_db() -> None:
    await engine.dispose()
