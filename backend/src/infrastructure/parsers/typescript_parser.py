from infrastructure.parsers.base_parser import TreeSitterParser

# Supports both JavaScript and TypeScript
_NAMES = frozenset(["javascript", "typescript", "js", "ts", "tsx", "jsx"])


class TypeScriptParser(TreeSitterParser):
    def __init__(self, *, use_tsx: bool = False) -> None:
        self._use_tsx = use_tsx
        super().__init__()

    @property
    def _lang_names(self) -> frozenset[str]:
        return _NAMES

    def _get_language(self):
        import tree_sitter_typescript as tsts  # noqa: PLC0415
        from tree_sitter import Language  # noqa: PLC0415

        return Language(tsts.language_tsx() if self._use_tsx else tsts.language_typescript())


class JavaScriptParser(TreeSitterParser):
    @property
    def _lang_names(self) -> frozenset[str]:
        return _NAMES

    def _get_language(self):
        import tree_sitter_javascript as tsjs  # noqa: PLC0415
        from tree_sitter import Language  # noqa: PLC0415

        return Language(tsjs.language())
