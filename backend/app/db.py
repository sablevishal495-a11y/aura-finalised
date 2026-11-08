"""One shared async database engine for every router."""
import os

from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://aura_user:aura_dev_password@localhost:5432/aura",
)

engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
