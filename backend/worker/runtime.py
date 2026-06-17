"""Event-driven worker runtime — sleeps until /wake, then drains Redis."""

from __future__ import annotations

import asyncio

import structlog

from infrastructure.config.settings import get_settings
from worker.drain import drain_queue, ensure_consumer_group

logger = structlog.get_logger()


class WorkerRuntime:
    def __init__(self) -> None:
        self._wake_event = asyncio.Event()
        self._running = False
        self._supervisor_task: asyncio.Task[None] | None = None

    def signal_wake(self) -> None:
        self._wake_event.set()

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._wake_event.set()  # drain any backlog left from a previous run
        self._supervisor_task = asyncio.create_task(self._supervisor_loop())
        await logger.ainfo("worker_runtime_started")

    async def stop(self) -> None:
        self._running = False
        self._wake_event.set()
        if self._supervisor_task is not None:
            await self._supervisor_task
            self._supervisor_task = None
        await logger.ainfo("worker_runtime_stopped")

    async def _supervisor_loop(self) -> None:
        settings = get_settings()
        redis = None
        use_redis = False

        if settings.upstash_redis_url and settings.upstash_redis_token:
            from upstash_redis import Redis

            redis = Redis(url=settings.upstash_redis_url, token=settings.upstash_redis_token)
            use_redis = True
            await asyncio.to_thread(ensure_consumer_group, redis, settings.redis_queue_stream)
        else:
            await logger.awarning("worker_redis_not_configured")

        while self._running:
            await self._wake_event.wait()
            self._wake_event.clear()

            if not use_redis or redis is None:
                continue

            await logger.ainfo("worker_drain_triggered")
            try:
                processed = await drain_queue(settings, redis)
                if processed == 0:
                    await logger.ainfo("worker_drain_empty")
            except Exception as exc:  # noqa: BLE001
                await logger.aerror(
                    "worker_drain_error",
                    error=str(exc) or repr(exc),
                    exc_type=type(exc).__name__,
                )
                await asyncio.sleep(1)  # backoff so a crash loop doesn't spin at full speed

            if self._wake_event.is_set():
                continue

        if use_redis:
            await logger.ainfo("worker_supervisor_exiting", stream=settings.redis_queue_stream)
