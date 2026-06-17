"""Tests for @trace_agent decorator and LangfuseClient."""
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from infrastructure.observability.langfuse_client import NoOpLangfuseClient, SpanContext
from infrastructure.observability.tracing import configure_tracing, trace_agent


@pytest.mark.asyncio
async def test_trace_agent_calls_start_and_end_span() -> None:
    client = MagicMock(spec=NoOpLangfuseClient)
    client.start_span.return_value = SpanContext(
        trace_id="t1", span_id="s1", name="test_agent"
    )
    configure_tracing(client)

    class FakeAgent:
        @trace_agent(name="test_agent")
        async def run(self, state: dict) -> dict:
            return {**state, "ran": True}

    agent = FakeAgent()
    state = {"trace_id": "t1"}
    result = await agent.run(state)

    assert result["ran"] is True
    client.start_span.assert_called_once_with("t1", name="test_agent")
    client.end_span.assert_called_once()


@pytest.mark.asyncio
async def test_trace_agent_records_error_on_exception() -> None:
    client = MagicMock(spec=NoOpLangfuseClient)
    client.start_span.return_value = SpanContext(
        trace_id="t2", span_id="s2", name="bad_agent"
    )
    configure_tracing(client)

    class BrokenAgent:
        @trace_agent(name="bad_agent")
        async def run(self, state: dict) -> dict:
            raise ValueError("something went wrong")

    agent = BrokenAgent()
    with pytest.raises(ValueError, match="something went wrong"):
        await agent.run({"trace_id": "t2"})

    # end_span should have been called with an error string
    call_kwargs = client.end_span.call_args.kwargs
    assert call_kwargs["error"] is not None
    assert "something went wrong" in call_kwargs["error"]


@pytest.mark.asyncio
async def test_noop_langfuse_client_returns_valid_ids() -> None:
    client = NoOpLangfuseClient()
    job_id = uuid4()

    trace_id = client.start_trace("review", job_id)
    assert trace_id.startswith("noop-")

    ctx = client.start_span(trace_id, "security")
    assert ctx.trace_id == trace_id
    assert ctx.name == "security"

    # Should not raise
    client.end_span(ctx, output={"duration_ms": 100})
    client.end_trace(trace_id, output={"total": 3})


def test_langfuse_client_uses_v4_observation_api() -> None:
    """LangfuseClient must use create_trace_id + start_observation (SDK v4)."""
    from unittest.mock import MagicMock, patch

    from infrastructure.observability.langfuse_client import LangfuseClient

    mock_lf = MagicMock()
    mock_lf.create_trace_id.return_value = "trace-abc"
    mock_root = MagicMock()
    mock_root.id = "root-span"
    mock_child = MagicMock()
    mock_child.id = "child-span"
    mock_lf.start_observation.side_effect = [mock_root, mock_child]

    with patch("langfuse.Langfuse", return_value=mock_lf):
        client = LangfuseClient(public_key="pk", secret_key="sk", host="https://cloud.langfuse.com")

    job_id = uuid4()
    trace_id = client.start_trace("review_pipeline", job_id)
    assert trace_id == "trace-abc"
    mock_lf.create_trace_id.assert_called_once()
    mock_lf.start_observation.assert_called()

    ctx = client.start_span(trace_id, "security_agent")
    assert ctx.span_id == "child-span"

    client.end_span(ctx, output={"duration_ms": 42})
    mock_child.update.assert_called_once_with(output={"duration_ms": 42})
    mock_child.end.assert_called_once()

    client.end_trace(trace_id, output={"total_findings": 3})
    mock_root.update.assert_called_once_with(output={"total_findings": 3})
    mock_root.end.assert_called_once()
    mock_lf.flush.assert_called_once()
