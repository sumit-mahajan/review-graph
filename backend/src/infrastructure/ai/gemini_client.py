"""
GeminiClient — wraps google-generativeai SDK.

All agent nodes call through this client — never import the SDK directly.
Handles:
  - Structured output via response_mime_type + Pydantic schema
  - Rate limit backoff: 429 → retry 2s / 8s / 32s (max 3 attempts)
  - Structured logging of token usage per call
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, TypeVar

import structlog
from pydantic import BaseModel

from domain.errors import ExternalServiceError

logger = structlog.get_logger()

T = TypeVar("T", bound=BaseModel)

BACKOFF_DELAYS = [2, 8, 32]
MODEL_ID = "gemini-2.5-flash"
EMBEDDING_MODEL_ID = "text-embedding-004"

# Metadata fields Gemini's response_schema does not accept.
_STRIP_FIELDS = {"title", "$schema", "default", "additionalProperties"}

# Keys that appear only in schema nodes (not in properties/field-name mappings).
# Used to distinguish "schema object" from "properties dict whose keys are field names".
_SCHEMA_KEYWORDS = {
    "type", "properties", "required", "items",
    "anyOf", "oneOf", "allOf", "enum", "$ref", "format", "nullable",
}


def _gemini_schema(schema: type[BaseModel]) -> dict[str, Any]:
    """Convert a Pydantic model to a Gemini-compatible JSON schema.

    Gemini rejects: title, $schema, default, additionalProperties.
    Gemini also does not support JSON Schema $ref/$defs — inline them.

    Note: only strips metadata keys from schema nodes (dicts whose own keys include
    schema keywords). This preserves property names like 'title' inside a
    `properties` mapping, where 'title' is a field name, not metadata.
    """
    raw = schema.model_json_schema()
    defs: dict[str, Any] = raw.pop("$defs", {})
    return _clean_node(raw, defs)  # type: ignore[return-value]


def _clean_node(node: Any, defs: dict[str, Any]) -> Any:
    if isinstance(node, list):
        return [_clean_node(item, defs) for item in node]
    if not isinstance(node, dict):
        return node
    # Inline $ref before anything else
    if "$ref" in node:
        ref_name = node["$ref"].split("/")[-1]
        return _clean_node(defs.get(ref_name, {}), defs)
    # Rewrite Pydantic's anyOf nullable pattern to Gemini's nullable:true form.
    # Pydantic emits: anyOf: [{type: X}, {type: null}]
    # Gemini wants:   {type: X, nullable: true}
    if "anyOf" in node:
        types = node["anyOf"]
        if isinstance(types, list) and len(types) == 2:
            null_variants = [t for t in types if t == {"type": "null"}]
            non_null = [t for t in types if t != {"type": "null"}]
            if null_variants and len(non_null) == 1:
                cleaned = _clean_node(non_null[0], defs)
                if isinstance(cleaned, dict):
                    return {**cleaned, "nullable": True}
    # Only strip metadata keys when this dict is itself a schema node (has schema
    # keywords). Property dicts like {"severity": {...}, "title": {...}} have
    # field names as keys and must not have those field names stripped.
    is_schema_node = bool(node.keys() & _SCHEMA_KEYWORDS)
    strip = _STRIP_FIELDS if is_schema_node else set()
    return {k: _clean_node(v, defs) for k, v in node.items() if k not in strip}


class GeminiClient:
    def __init__(self, api_key: str) -> None:
        import google.generativeai as genai  # lazy — optional in tests

        genai.configure(api_key=api_key)
        self._genai = genai
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

        generation_config = self._genai.GenerationConfig(
            temperature=temperature,
            response_mime_type="application/json",
            response_schema=schema_json,
        )

        model = self._genai.GenerativeModel(
            model_name=self._model_id,
            generation_config=generation_config,
            system_instruction=system_prompt,
        )

        messages = [{"role": "user", "parts": [prompt]}]

        for attempt, delay in enumerate([0, *BACKOFF_DELAYS]):
            if delay:
                await asyncio.sleep(delay)
            try:
                response = await asyncio.to_thread(model.generate_content, messages)
                _log_usage(response, schema.__name__)
                return schema.model_validate_json(response.text)

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

        raise ExternalServiceError("Gemini exhausted all retries")  # unreachable but mypy-safe

    async def embed(self, text: str) -> list[float]:
        """Generate a 768-dim embedding vector using Gemini text-embedding-004."""
        model = self._genai.embed_content

        for attempt, delay in enumerate([0, *BACKOFF_DELAYS]):
            if delay:
                await asyncio.sleep(delay)
            try:
                result = await asyncio.to_thread(
                    model,
                    model=EMBEDDING_MODEL_ID,
                    content=text,
                    task_type="retrieval_document",
                )
                return list(result["embedding"])
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
            import structlog as _sl  # noqa: PLC0415
            import asyncio as _asyncio  # noqa: PLC0415
            _asyncio.create_task(
                _sl.get_logger().ainfo(
                    "gemini_usage",
                    schema=schema_name,
                    prompt_tokens=getattr(usage, "prompt_token_count", 0),
                    output_tokens=getattr(usage, "candidates_token_count", 0),
                )
            )
    except Exception:  # noqa: BLE001
        pass
