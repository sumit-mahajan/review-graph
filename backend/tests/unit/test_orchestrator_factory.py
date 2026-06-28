"""Tests for orchestrator factory."""

from unittest.mock import MagicMock

from infrastructure.ai.langgraph_orchestrator import LanggraphOrchestrator
from infrastructure.ai.orchestrator_factory import build_orchestrator
from infrastructure.ai.stub_orchestrator import StubAgentOrchestrator
from infrastructure.config.settings import Settings


def test_build_orchestrator_returns_stub_without_gemini_key() -> None:
    settings = Settings(GEMINI_API_KEY=None)
    orchestrator = build_orchestrator(settings, MagicMock(), MagicMock())
    assert isinstance(orchestrator, StubAgentOrchestrator)


def test_build_orchestrator_returns_langgraph_with_gemini_key() -> None:
    settings = Settings(
        GEMINI_API_KEY="test-key",
        GITHUB_APP_ID="123",
        GITHUB_APP_PRIVATE_KEY_B64="dGVzdA==",
    )
    orchestrator = build_orchestrator(settings, MagicMock(), MagicMock())
    assert isinstance(orchestrator, LanggraphOrchestrator)
