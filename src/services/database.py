"""SQLAlchemy 异步引擎 + 会话管理"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.models.base import Base

def _get_config_url() -> str:
    """延迟加载数据库 URL，避免在模块导入时执行"""
    from src.config import load_config
    return load_config().database.url

_engine = create_async_engine(
    _get_config_url(),
    connect_args={"check_same_thread": False},
)

_async_session = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


async def init_db(engine=None):
    """创建所有表并启用 WAL 和外键约束。

    在 bot startup 时调用，确保表结构存在。
    """
    if engine is None:
        engine = _engine
    async with engine.begin() as conn:
        await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        await conn.exec_driver_sql("PRAGMA foreign_keys=ON")
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def get_db_session(session_maker=None) -> AsyncIterator[AsyncSession]:
    """获取数据库会话的异步上下文管理器。

    退出时自动 commit；异常时自动 rollback 并向外传播异常。
    """
    maker = session_maker or _async_session
    async with maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
