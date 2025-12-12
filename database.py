from __future__ import annotations
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()
engine = create_async_engine(
    "sqlite+aiosqlite:///./tasks.db"
)
DBSession = sessionmaker(bind=engine, autoflush=False,
                         autocommit=False, class_=AsyncSession)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    db = DBSession()
    try:
        yield db
    finally:
        await db.close()
