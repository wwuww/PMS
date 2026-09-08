"""异步数据库会话（SQLAlchemy 2.0 async）。

生产环境为 PostgreSQL（asyncpg）；开发/测试默认 SQLite（aiosqlite），
切换仅需修改 PMS_DATABASE_URL，业务代码零改动。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _configure_sqlite_connection(dbapi_conn, conn_record) -> None:  # noqa: ANN001
    """SQLite 并发优化（仅 dev/test 用 aiosqlite 时生效）：

    - WAL：读者不阻塞写者、写者不阻塞读者，避免全局 Webhook 投递器在事务
      期间开新连接做 SELECT 时与调用方未提交事务发生锁等待死锁（Sprint 13 副作用）。
    - busy_timeout：极端写竞争下优雅等待而非立即报 "database is locked"。
    """
    try:
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=10000")
        cur.close()
    except Exception:  # noqa: BLE001
        pass


def get_engine() -> AsyncEngine:
    """懒加载引擎（测试可重置以切换数据库文件）。

    M30 连接池参数化：SQLite 无连接池语义（文件库），不传池参数；
    MySQL/PostgreSQL 按 Settings 应用 pool_size/max_overflow/pool_recycle/pool_timeout，
    解决高并发下连接耗尽与 MySQL 8h wait_timeout 静默断连问题。
    """
    global _engine, _session_factory
    if _engine is None:
        settings = get_settings()
        url = settings.database_url
        engine_kwargs: dict[str, Any] = {"pool_pre_ping": True}
        is_sqlite = str(url).startswith("sqlite")
        if not is_sqlite:
            engine_kwargs.update(
                pool_size=settings.db_pool_size,
                max_overflow=settings.db_max_overflow,
                pool_timeout=settings.db_pool_timeout,
            )
            if settings.db_pool_recycle > 0:
                engine_kwargs["pool_recycle"] = settings.db_pool_recycle
        _engine = create_async_engine(url, **engine_kwargs)
        _session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
        if is_sqlite:
            event.listen(_engine.sync_engine, "connect", _configure_sqlite_connection)
    return _engine


def reset_engine() -> None:
    """重置引擎（测试隔离用；生产勿调用）。"""
    global _engine, _session_factory
    _engine = None
    _session_factory = None


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖：每请求一个会话。"""
    get_engine()
    assert _session_factory is not None
    async with _session_factory() as session:
        yield session


async def init_db() -> None:
    """开发模式建表；生产使用 Alembic 迁移（Sprint 2 引入）。"""
    from app.models import Base  # noqa: PLC0415

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
