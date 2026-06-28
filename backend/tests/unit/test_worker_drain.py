"""Tests for worker queue drain helpers."""

import json

from worker.drain import _stream_payload


def test_stream_payload_from_upstash_flat_list() -> None:
    fields = [
        "payload",
        json.dumps({"job_type": "review", "job_id": "abc"}),
    ]
    assert json.loads(_stream_payload(fields))["job_type"] == "review"


def test_stream_payload_from_redis_py_dict() -> None:
    fields = {"payload": json.dumps({"job_type": "review"})}
    assert json.loads(_stream_payload(fields))["job_type"] == "review"


def test_stream_payload_missing_returns_empty_object() -> None:
    assert _stream_payload([]) == "{}"
