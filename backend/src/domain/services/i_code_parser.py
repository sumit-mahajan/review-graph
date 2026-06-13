from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedNode:
    node_type: str     # function | class | module
    node_name: str
    start_line: int    # 1-indexed
    end_line: int
    body: str


class ICodeParser(ABC):
    """Parses source code into semantic nodes (functions, classes)."""

    @abstractmethod
    def supports(self, language: str) -> bool:
        """Return True if this parser handles the given language."""

    @abstractmethod
    def parse(self, source: str) -> list[ParsedNode]:
        """Extract function/class nodes from source code."""
