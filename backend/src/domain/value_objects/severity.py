from enum import StrEnum


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


_SEVERITY_RANK: dict[Severity, int] = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
    Severity.INFO: 4,
}


def severity_meets_minimum(severity: Severity, minimum: Severity) -> bool:
    """Return True when severity is at or above the configured minimum."""
    return _SEVERITY_RANK[severity] <= _SEVERITY_RANK[minimum]


def parse_severity(value: str, *, default: Severity = Severity.MEDIUM) -> Severity:
    try:
        return Severity(value.lower())
    except ValueError:
        return default
