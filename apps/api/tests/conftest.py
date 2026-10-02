from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.application import create_app
from app.core.config import Settings


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app(Settings(app_env="test"))
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as test_client:
        yield test_client
