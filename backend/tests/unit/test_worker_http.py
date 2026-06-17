from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from infrastructure.config.settings import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def worker_secret(monkeypatch: pytest.MonkeyPatch) -> str:
    secret = "test-worker-secret"
    monkeypatch.setenv("WORKER_WAKE_SECRET", secret)
    get_settings.cache_clear()
    return secret


@pytest.fixture
async def worker_client(monkeypatch: pytest.MonkeyPatch) -> AsyncClient:
    monkeypatch.setattr("worker.http.runtime.start", AsyncMock())
    monkeypatch.setattr("worker.http.runtime.stop", AsyncMock())

    transport = ASGITransport(app=__import__("worker.http", fromlist=["app"]).app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_wake_rejects_invalid_secret(worker_client: AsyncClient, worker_secret: str) -> None:
    response = await worker_client.post("/wake", headers={"X-Worker-Secret": "wrong"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_wake_accepts_valid_secret(
    worker_client: AsyncClient, worker_secret: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    signal_wake = MagicMock()
    monkeypatch.setattr("worker.http.runtime.signal_wake", signal_wake)

    response = await worker_client.post(
        "/wake",
        headers={"X-Worker-Secret": worker_secret},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "accepted"}
    signal_wake.assert_called_once()


@pytest.mark.asyncio
async def test_worker_health(worker_client: AsyncClient) -> None:
    response = await worker_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
