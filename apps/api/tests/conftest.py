from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.application import create_app
from app.core.config import Settings
from app.db.session import get_database_session

TEST_DATABASE_URL = (
    "postgresql+asyncpg://ai_profit_monitor:local_development_only@localhost:5437/"
    "ai_profit_monitor_test"
)


@pytest.fixture
async def test_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE TABLE usage_events, project_api_keys, projects, "
                "sessions, memberships, organizations, users CASCADE"
            )
        )
    yield engine
    await engine.dispose()


@pytest.fixture
def app(test_engine: AsyncEngine) -> Any:
    application = create_app(
        Settings(
            app_env="test",
            database_url=TEST_DATABASE_URL,
            cors_origins=["http://localhost:3000"],
            session_cookie_domain="",
            session_last_used_update_seconds=300,
        )
    )
    session_maker = async_sessionmaker(test_engine, expire_on_commit=False)

    async def test_session() -> AsyncIterator[AsyncSession]:
        async with session_maker() as session:
            yield session

    application.dependency_overrides[get_database_session] = test_session
    return application


@pytest.fixture
async def client(app: Any) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as test_client:
        yield test_client


@pytest.fixture
async def db(test_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    session_maker = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_maker() as session:
        yield session
