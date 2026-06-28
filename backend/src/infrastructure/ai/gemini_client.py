"""
GeminiClient — wraps the google-genai SDK.

All agent nodes call through this client — never import the SDK directly.
Handles:
  - Structured output via response_mime_type + response_json_schema
  - Rate limit backoff: 429 → retry 2s / 8s / 32s (max 3 attempts)
  - Structured logging of token usage per call
"""

from __future__ import annotations

import asyncio
from typing import Any, TypeVar

import structlog
from pydantic import BaseModel

from domain.errors import ExternalServiceError

logger = structlog.get_logger()

T = TypeVar("T", bound=BaseModel)

BACKOFF_DELAYS = [2, 8, 32]
MODEL_ID = "gemini-2.5-flash"
EMBEDDING_MODEL_ID = "gemini-embedding-001"
EMBEDDING_DIMENSION = 768

# Metadata fields Gemini's response schema does not accept.
_STRIP_FIELDS = {"title", "$schema", "default", "additionalProperties"}

# Keys that appear only in schema nodes (not in properties/field-name mappings).
_SCHEMA_KEYWORDS = {
    "type",
    "properties",
    "required",
    "items",
    "anyOf",
    "oneOf",
    "allOf",
    "enum",
    "$ref",
    "format",
    "nullable",
}


def _gemini_schema(schema: type[BaseModel]) -> dict[str, Any]:
    """Convert a Pydantic model to a Gemini-compatible JSON schema."""
    raw = schema.model_json_schema()
    defs: dict[str, Any] = raw.pop("$defs", {})
    return _clean_node(raw, defs)  # type: ignore[no-any-return]


def _clean_node(node: Any, defs: dict[str, Any]) -> Any:
    if isinstance(node, list):
        return [_clean_node(item, defs) for item in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        ref_name = node["$ref"].split("/")[-1]
        return _clean_node(defs.get(ref_name, {}), defs)
    if "anyOf" in node:
        types = node["anyOf"]
        if isinstance(types, list) and len(types) == 2:
            null_variants = [t for t in types if t == {"type": "null"}]
            non_null = [t for t in types if t != {"type": "null"}]
            if null_variants and len(non_null) == 1:
                cleaned = _clean_node(non_null[0], defs)
                if isinstance(cleaned, dict):
                    return {**cleaned, "nullable": True}
    is_schema_node = bool(node.keys() & _SCHEMA_KEYWORDS)
    strip = _STRIP_FIELDS if is_schema_node else set()
    return {k: _clean_node(v, defs) for k, v in node.items() if k not in strip}


class GeminiClient:
    def __init__(self, api_key: str) -> None:
        from google import genai
        from google.genai import types

        self._types = types
        self._client = genai.Client(api_key=api_key)
        self._model_id = MODEL_ID

    async def generate(
        self,
        prompt: str,
        schema: type[T],
        *,
        system_prompt: str | None = None,
        temperature: float = 0.1,
    ) -> T:
        """Call Gemini with structured output enforced by Pydantic schema."""
        schema_json = _gemini_schema(schema)
        config_kwargs: dict[str, Any] = {
            "temperature": temperature,
            "response_mime_type": "application/json",
            "response_json_schema": schema_json,
        }
        if system_prompt is not None:
            config_kwargs["system_instruction"] = system_prompt

        config = self._types.GenerateContentConfig(**config_kwargs)

        for attempt, delay in enumerate([0, *BACKOFF_DELAYS]):
            if delay:
                await asyncio.sleep(delay)
            try:
                response = await self._client.aio.models.generate_content(
                    model=self._model_id,
                    contents=prompt,
                    config=config,
                )
                _log_usage(response, schema.__name__)
                if not response.text:
                    raise ExternalServiceError("Gemini returned empty response")
                return schema.model_validate_json(response.text)

            except ExternalServiceError:
                raise
            except Exception as exc:
                exc_str = str(exc)
                is_rate_limit = "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str.upper()
                is_last = attempt == len(BACKOFF_DELAYS)

                if is_rate_limit and not is_last:
                    await logger.awarning(
                        "gemini_rate_limited",
                        attempt=attempt + 1,
                        next_delay=BACKOFF_DELAYS[attempt] if attempt < len(BACKOFF_DELAYS) else 0,
                    )
                    continue

                await logger.aerror(
                    "gemini_call_failed",
                    schema=schema.__name__,
                    attempt=attempt + 1,
                    error=exc_str[:300],
                )
                raise ExternalServiceError(f"Gemini call failed: {exc_str[:200]}") from exc

        raise ExternalServiceError("Gemini exhausted all retries")

    async def embed(
        self,
        text: str,
        *,
        task_type: str = "RETRIEVAL_DOCUMENT",
    ) -> list[float]:
        """Generate a 768-dim embedding vector using gemini-embedding-001."""
        normalized = text.strip()
        if not normalized:
            raise ExternalServiceError("Gemini embed failed: empty text")

        config = self._types.EmbedContentConfig(
            task_type=task_type,
            output_dimensionality=EMBEDDING_DIMENSION,
        )

        for attempt, delay in enumerate([0, *BACKOFF_DELAYS]):
            if delay:
                await asyncio.sleep(delay)
            try:
                result = await self._client.aio.models.embed_content(
                    model=EMBEDDING_MODEL_ID,
                    contents=normalized,
                    config=config,
                )
                if not result.embeddings or result.embeddings[0].values is None:
                    raise ExternalServiceError("Gemini embed returned no vector")
                return list(result.embeddings[0].values)
            except ExternalServiceError:
                raise
            except Exception as exc:
                exc_str = str(exc)
                is_rate_limit = "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str.upper()
                is_last = attempt == len(BACKOFF_DELAYS)
                if is_rate_limit and not is_last:
                    continue
                raise ExternalServiceError(f"Gemini embed failed: {exc_str[:200]}") from exc

        raise ExternalServiceError("Gemini embed exhausted all retries")


def _log_usage(response: Any, schema_name: str) -> None:
    try:
        usage = getattr(response, "usage_metadata", None)
        if usage:
            import asyncio as _asyncio

            _asyncio.create_task(
                logger.ainfo(
                    "gemini_usage",
                    schema=schema_name,
                    prompt_tokens=getattr(usage, "prompt_token_count", 0),
                    output_tokens=getattr(usage, "candidates_token_count", 0),
                )
            )
    except Exception as exc:  # noqa: BLE001
        logger.debug("gemini_usage_log_failed", schema=schema_name, error=str(exc))
