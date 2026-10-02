from collections.abc import AsyncIterator
from typing import Any

from httpx import AsyncClient

from app.core.application import create_app
from app.core.config import Settings
from app.db.session import get_database_session


class AvailableSession:
    async def execute(self, _statement: Any) -> None:
        return None


class UnavailableSession:
    async def execute(self, _statement: Any) -> None:
        raise ConnectionError("database unavailable")


async def test_health_does_not_require_database(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"success": True, "data": {"status": "healthy"}}


async def test_ready_when_database_is_available() -> None:
    app = create_app(Settings(app_env="test"))

    async def available_session() -> AsyncIterator[AvailableSession]:
        yield AvailableSession()

    app.dependency_overrides[get_database_session] = available_session

    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "data": {"status": "ready", "database": "available"},
    }


async def test_ready_when_database_is_unavailable() -> None:
    app = create_app(Settings(app_env="test"))

    async def unavailable_session() -> AsyncIterator[UnavailableSession]:
        yield UnavailableSession()

    app.dependency_overrides[get_database_session] = unavailable_session

    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "success": False,
        "data": {"status": "not_ready", "database": "unavailable"},
    }
