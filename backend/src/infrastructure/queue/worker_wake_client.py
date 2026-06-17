import structlog

from domain.services.i_worker_wake_client import IWorkerWakeClient

logger = structlog.get_logger()


class NoOpWorkerWakeClient(IWorkerWakeClient):
    """Used when WORKER_WAKE_URL is not configured (tests, local without worker)."""

    async def wake(self) -> None:
        return


class HttpWorkerWakeClient(IWorkerWakeClient):
    """POST to the worker /wake endpoint after enqueueing a job."""

    def __init__(self, wake_url: str | None, wake_secret: str | None) -> None:
        self._wake_url = (wake_url or "").strip()
        self._wake_secret = (wake_secret or "").strip()

    async def wake(self) -> None:
        if not self._wake_url or not self._wake_secret:
            await logger.awarning("worker_wake_skipped_not_configured")
            return

        try:
            import httpx

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    self._wake_url,
                    headers={"X-Worker-Secret": self._wake_secret},
                )
                response.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            await logger.aerror(
                "worker_wake_failed",
                error=str(exc) or repr(exc),
                exc_type=type(exc).__name__,
            )
