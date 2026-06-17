"""Drain review jobs from the Upstash Redis stream."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

import structlog

from infrastructure.config.settings import Settings
from worker.dispatcher_factory import dispatch_payload

if TYPE_CHECKING:
    from upstash_redis import Redis

logger = structlog.get_logger()

CONSUMER_GROUP = "workers"
CONSUMER_NAME = "worker-1"


def _stream_payload(fields: object) -> str:
    """Normalize Upstash (flat list) and redis-py (dict) stream field shapes."""
    if isinstance(fields, dict):
        raw = fields.get("payload") or fields.get(b"payload")
    elif isinstance(fields, list):
        raw = None
        for index in range(0, len(fields) - 1, 2):
            key = fields[index]
            if isinstance(key, bytes):
                key = key.decode()
            if key == "payload":
                raw = fields[index + 1]
                break
    else:
        raw = None

    if raw is None:
        return "{}"
    if isinstance(raw, bytes):
        return raw.decode()
    return str(raw)


async def drain_queue(settings: Settings, redis: Redis) -> int:
    """Process all pending messages in the stream. Returns count processed."""
    stream = settings.redis_queue_stream
    processed = 0

    # "0" = this consumer's unacked (PEL) entries; ">" = never-delivered entries.
    for stream_id in ("0", ">"):
        while True:
            try:
                entries = await asyncio.to_thread(
                    redis.xreadgroup,
                    CONSUMER_GROUP,
                    CONSUMER_NAME,
                    {stream: stream_id},
                    count=1,
                )
            except Exception as exc:  # noqa: BLE001
                await logger.aerror(
                    "worker_xreadgroup_error",
                    stream_id=stream_id,
                    error=str(exc) or repr(exc),
                    exc_type=type(exc).__name__,
                )
                break  # stop this stream_id pass; move on

            # Upstash may return [['streamname', []]] when PEL is empty instead of [].
            # Flatten to get actual messages across all entries.
            all_messages = [
                (msg_id, fields)
                for _sn, msgs in (entries or [])
                for msg_id, fields in (msgs or [])
            ]

            if not all_messages:
                await logger.ainfo("worker_drain_read", stream_id=stream_id, found=0)
                break

            await logger.ainfo("worker_drain_read", stream_id=stream_id, found=len(all_messages))

            count, should_continue = await _process_entries(settings, redis, stream, all_messages)
            processed += count
            if not should_continue:
                break

    if processed:
        await logger.ainfo("worker_drain_complete", processed=processed)

    return processed


async def _process_entries(
    settings: Settings, redis: Redis, stream: str, messages: list[object]
) -> tuple[int, bool]:
    """Process a flat list of (msg_id, fields) tuples."""
    processed = 0

    for msg_id, fields in messages:
        raw = _stream_payload(fields)
        try:
            job_type = json.loads(raw).get("job_type", "unknown")
        except Exception:
            job_type = "parse_error"
        await logger.ainfo("worker_dispatching", msg_id=str(msg_id), job_type=job_type)

        try:
            acked = await dispatch_payload(settings, str(raw))
        except Exception as exc:  # noqa: BLE001
            await logger.aerror(
                "worker_dispatch_error",
                error=str(exc) or repr(exc),
                exc_type=type(exc).__name__,
                msg_id=str(msg_id),
            )
            acked = False

        if acked:
            await asyncio.to_thread(redis.xack, stream, CONSUMER_GROUP, msg_id)
            processed += 1
        else:
            # Stop this drain cycle so unacked PEL entries are not hot-looped.
            return processed, False

    return processed, True


def ensure_consumer_group(redis: Redis, stream: str) -> None:
    try:
        redis.xgroup_create(stream, CONSUMER_GROUP, id="0", mkstream=True)
    except Exception:  # noqa: BLE001
        pass  # Group already exists
