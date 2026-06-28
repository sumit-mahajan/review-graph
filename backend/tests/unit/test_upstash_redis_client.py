"""Tests for UpstashRedisClient.enqueue."""

import json
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from domain.services.i_queue_client import QueueMessage
from domain.value_objects.job_type import JobType
from infrastructure.queue.upstash_redis_client import UpstashRedisClient


@pytest.mark.asyncio
async def test_enqueue_calls_xadd_with_stream_id_and_payload() -> None:
    mock_redis = MagicMock()
    mock_redis.xadd.return_value = "1781727511285-0"

    message = QueueMessage(
        job_type=JobType.REVIEW,
        job_id=uuid4(),
        repository_id=uuid4(),
        head_sha="abc123",
        pr_number=1,
    )

    with patch("upstash_redis.Redis", return_value=mock_redis):
        client = UpstashRedisClient(
            redis_url="https://example.upstash.io",
            redis_token="token",
            stream_name="review_jobs",
        )

    message_id = await client.enqueue(message)

    assert message_id == "1781727511285-0"
    mock_redis.xadd.assert_called_once()
    args = mock_redis.xadd.call_args.args
    assert args[0] == "review_jobs"
    assert args[1] == "*"
    assert json.loads(args[2]["payload"])["job_type"] == JobType.REVIEW.value
