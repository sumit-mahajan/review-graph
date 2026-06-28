"""Tests for JWT service."""

from uuid import uuid4

import pytest

from domain.errors import DomainError
from infrastructure.auth.jwt_service import JwtService


def test_create_and_decode_token() -> None:
    service = JwtService(secret="test-secret-key-at-least-32-chars-long", expire_days=7)
    user_id = uuid4()
    token = service.create_token(user_id=user_id, github_id=42, login="dev")
    payload = service.decode_token(token)
    assert payload.sub == user_id
    assert payload.github_id == 42
    assert payload.login == "dev"


def test_decode_invalid_token_raises() -> None:
    service = JwtService(secret="test-secret-key-at-least-32-chars-long")
    with pytest.raises(DomainError):
        service.decode_token("not-a-valid-token")
