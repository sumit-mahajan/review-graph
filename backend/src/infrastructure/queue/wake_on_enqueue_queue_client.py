from domain.services.i_queue_client import IQueueClient, QueueMessage
from domain.services.i_worker_wake_client import IWorkerWakeClient


class WakeOnEnqueueQueueClient(IQueueClient):
    """Enqueue to Redis, then signal the worker to drain (no idle polling)."""

    def __init__(self, inner: IQueueClient, wake_client: IWorkerWakeClient) -> None:
        self._inner = inner
        self._wake = wake_client

    async def enqueue(self, message: QueueMessage) -> str:
        message_id = await self._inner.enqueue(message)
        await self._wake.wake()
        return message_id
