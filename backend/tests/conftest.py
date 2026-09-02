"""Isolated API test fixtures."""
from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base, apply_sqlite_pragmas, get_db
from app.main import app
from app.models import all_models  # noqa: F401


def _apply_pragmas(sync_conn) -> None:
    # Mirror the engine's connect listener so tests exercise the same
    # constraints as production (notably foreign_keys=ON).
    cursor = sync_conn.cursor()
    try:
        apply_sqlite_pragmas(cursor)
    finally:
        cursor.close()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _pragma(dbapi_conn, connection_record):  # noqa: ANN001, ANN202
        cursor = dbapi_conn.cursor()
        try:
            apply_sqlite_pragmas(cursor)
        finally:
            cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def api_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
