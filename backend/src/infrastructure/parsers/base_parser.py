"""
Abstract base for tree-sitter parsers. Shared extraction logic lives here.
"""
from __future__ import annotations

from domain.services.i_code_parser import ICodeParser, ParsedNode

# Node type labels for tree-sitter grammar types → our canonical names
FUNCTION_TYPES = frozenset([
    "function_definition",    # Python
    "function_declaration",   # JS/TS
    "method_definition",      # JS/TS class methods
    "arrow_function",         # JS/TS
    "async_function_expression",
])

CLASS_TYPES = frozenset([
    "class_definition",       # Python
    "class_declaration",      # JS/TS
])

ANONYMOUS_NAMES = frozenset(["anonymous", "", None])


class TreeSitterParser(ICodeParser):
    """Base tree-sitter parser. Subclasses supply `_language` and `_lang_names`."""

    def __init__(self) -> None:
        from tree_sitter import Parser  # noqa: PLC0415

        self._parser = Parser(self._get_language())

    def _get_language(self):  # type: ignore[return]
        raise NotImplementedError

    @property
    def _lang_names(self) -> frozenset[str]:
        raise NotImplementedError

    def supports(self, language: str) -> bool:
        return language.lower() in self._lang_names

    def parse(self, source: str) -> list[ParsedNode]:
        source_bytes = source.encode("utf-8")
        tree = self._parser.parse(source_bytes)
        nodes: list[ParsedNode] = []
        self._walk(tree.root_node, source_bytes, nodes)
        return nodes

    def _walk(self, node: object, source_bytes: bytes, out: list[ParsedNode]) -> None:
        from tree_sitter import Node  # noqa: PLC0415

        assert isinstance(node, Node)

        if node.type in FUNCTION_TYPES or node.type in CLASS_TYPES:
            canonical_type = "function" if node.type in FUNCTION_TYPES else "class"
            name = self._extract_name(node, source_bytes)
            if name and name not in ANONYMOUS_NAMES:
                body = source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
                # Trim very large functions to stay within token budget
                if len(body) > 12000:
                    body = body[:6000] + "\n...[truncated]...\n" + body[-1000:]
                out.append(ParsedNode(
                    node_type=canonical_type,
                    node_name=name,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    body=body,
                ))
        for child in node.children:
            self._walk(child, source_bytes, out)

    @staticmethod
    def _extract_name(node: object, source_bytes: bytes) -> str | None:
        from tree_sitter import Node  # noqa: PLC0415

        assert isinstance(node, Node)
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            return source_bytes[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
        return None
