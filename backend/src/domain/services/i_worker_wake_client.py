from abc import ABC, abstractmethod


class IWorkerWakeClient(ABC):
    """Notify the worker process to drain the Redis job queue."""

    @abstractmethod
    async def wake(self) -> None:
        """Signal the worker to process pending queue messages."""
