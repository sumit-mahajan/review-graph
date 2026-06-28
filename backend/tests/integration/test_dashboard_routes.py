"""Dashboard API route tests — auth enforcement."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.middleware.auth_middleware import get_current_user
from domain.entities.user import User


def _test_user() -> User:
    now = datetime.now(UTC)
    return User(
        id=uuid4(),
        github_id=1,
        login="dev",
        email=None,
        avatar_url=None,
        created_at=now,
        updated_at=now,
    )


def test_list_repos_requires_auth() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/repos")
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "UNAUTHORIZED"


def test_list_repos_returns_empty_with_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    from application.use_cases.list_repos import ListReposUseCase

    async def _fake_execute(self: object, user: object) -> list:
        return []

    monkeypatch.setattr(ListReposUseCase, "execute", _fake_execute)

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: _test_user()  # type: ignore[misc]
    client = TestClient(app)

    response = client.get("/api/v1/repos")
    assert response.status_code == 200
    assert response.json() == []
