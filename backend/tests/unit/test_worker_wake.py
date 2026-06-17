from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from domain.services.i_queue_client import QueueMessage
from domain.value_objects.job_type import JobType
from infrastructure.queue.wake_on_enqueue_queue_client import WakeOnEnqueueQueueClient
from infrastructure.queue.worker_wake_client import HttpWorkerWakeClient, NoOpWorkerWakeClient
from uuid import uuid4


@pytest.mark.asyncio
async def test_wake_on_enqueue_calls_wake_after_enqueue() -> None:
    inner = AsyncMock()
    inner.enqueue.return_value = "msg-1"
    wake = AsyncMock()

    client = WakeOnEnqueueQueueClient(inner, wake)
    message = QueueMessage(
        job_type=JobType.REVIEW,
        job_id=uuid4(),
        repository_id=uuid4(),
        head_sha="a" * 40,
        pr_number=1,
    )

    result = await client.enqueue(message)

    assert result == "msg-1"
    inner.enqueue.assert_awaited_once_with(message)
    wake.wake.assert_awaited_once()


@pytest.mark.asyncio
async def test_noop_wake_client_does_nothing() -> None:
    client = NoOpWorkerWakeClient()
    await client.wake()


@pytest.mark.asyncio
async def test_http_wake_client_skips_when_not_configured() -> None:
    client = HttpWorkerWakeClient(None, None)
    await client.wake()


@pytest.mark.asyncio
async def test_http_wake_client_posts_to_worker() -> None:
    client = HttpWorkerWakeClient("http://worker:8001/wake", "secret")

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    mock_http = AsyncMock()
    mock_http.post.return_value = mock_response
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_http):
        await client.wake()

    mock_http.post.assert_awaited_once_with(
        "http://worker:8001/wake",
        headers={"X-Worker-Secret": "secret"},
    )
