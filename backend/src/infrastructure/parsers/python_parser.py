from typing import Any

from infrastructure.parsers.base_parser import TreeSitterParser


class PythonParser(TreeSitterParser):
    @property
    def _lang_names(self) -> frozenset[str]:
        return frozenset(["python", "py"])

    def _get_language(self) -> Any:
        import tree_sitter_python as tspython  # noqa: PLC0415
        from tree_sitter import Language  # noqa: PLC0415

        return Language(tspython.language())
