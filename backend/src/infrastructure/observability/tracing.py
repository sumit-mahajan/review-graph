"""
@trace_agent decorator — wraps an async agent node function with a Langfuse span.

Usage:
    @trace_agent(name="security_agent")
    async def run(self, state: ReviewState) -> ReviewState:
        ...

The decorator reads the Langfuse trace_id from state["trace_id"] and
records span start/end with token usage and latency automatically.
"""

from __future__ import annotations

import functools
import time
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

import structlog

from infrastructure.observability.langfuse_client import ILangfuseClient, NoOpLangfuseClient

logger = structlog.get_logger()

# Module-level client; replaced at startup via configure_tracing()
_client: ILangfuseClient = NoOpLangfuseClient()


def configure_tracing(client: ILangfuseClient) -> None:
    """Inject the real Langfuse client at app startup."""
    global _client  # noqa: PLW0603
    _client = client


F = TypeVar("F", bound=Callable[..., Coroutine[Any, Any, Any]])


def trace_agent(name: str) -> Callable[[F], F]:
    """Decorator factory that wraps an async agent method with a Langfuse span."""

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Expect first positional arg to be the agent instance (self),
            # second to be the ReviewState dict.
            state: dict[str, Any] = args[1] if len(args) > 1 else kwargs.get("state", {})
            trace_id: str | None = state.get("trace_id") if isinstance(state, dict) else None

            ctx = _client.start_span(trace_id or "no-trace", name=name)
            start = time.monotonic()
            error_msg: str | None = None

            try:
                return await fn(*args, **kwargs)
            except Exception as exc:
                error_msg = f"{type(exc).__name__}: {exc}"
                raise
            finally:
                elapsed_ms = int((time.monotonic() - start) * 1000)
                _client.end_span(
                    ctx,
                    output={"duration_ms": elapsed_ms},
                    error=error_msg,
                )
                log = logger.bind(agent=name, duration_ms=elapsed_ms)
                if error_msg:
                    await log.aerror("agent_span_failed", error=error_msg)
                else:
                    await log.ainfo("agent_span_completed")

        return wrapper  # type: ignore[return-value]

    return decorator
