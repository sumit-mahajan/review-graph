"""Tests for severity helpers."""

from domain.value_objects.severity import Severity, parse_severity, severity_meets_minimum


def test_severity_meets_minimum() -> None:
    assert severity_meets_minimum(Severity.CRITICAL, Severity.MEDIUM) is True
    assert severity_meets_minimum(Severity.HIGH, Severity.MEDIUM) is True
    assert severity_meets_minimum(Severity.MEDIUM, Severity.MEDIUM) is True
    assert severity_meets_minimum(Severity.LOW, Severity.MEDIUM) is False
    assert severity_meets_minimum(Severity.INFO, Severity.HIGH) is False


def test_parse_severity_defaults_on_invalid() -> None:
    assert parse_severity("bogus") == Severity.MEDIUM
    assert parse_severity("high") == Severity.HIGH
