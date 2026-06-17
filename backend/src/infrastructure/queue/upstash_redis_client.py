import json

import structlog

from domain.errors import ExternalServiceError
from domain.services.i_queue_client import IQueueClient, QueueMessage
from infrastructure.queue.in_memory_queue_client import InMemoryQueueClient

logger = structlog.get_logger()


class UpstashRedisClient(IQueueClient):
    """Enqueue review jobs to Upstash Redis Streams."""

    def __init__(
        self,
        redis_url: str | None,
        redis_token: str | None,
        stream_name: str = "review_jobs",
    ) -> None:
        self._stream_name = stream_name
        self._fallback = InMemoryQueueClient()
        self._redis = None

        if redis_url and redis_token:
            try:
                from upstash_redis import Redis

                self._redis = Redis(url=redis_url, token=redis_token)
            except Exception as exc:  # noqa: BLE001
                raise ExternalServiceError("Failed to initialize Upstash Redis client") from exc

    async def enqueue(self, message: QueueMessage) -> str:
        payload = InMemoryQueueClient.serialize(message)

        if self._redis is None:
            await logger.awarning("redis_not_configured_using_in_memory_queue")
            return await self._fallback.enqueue(message)

        try:
            message_id: str = self._redis.xadd(
                self._stream_name, "*", {"payload": payload}
            )
            return message_id
        except Exception as exc:  # noqa: BLE001
            raise ExternalServiceError("Failed to enqueue job to Redis") from exc

    @staticmethod
    def parse_payload(raw: str) -> dict[str, object]:
        return json.loads(raw)
