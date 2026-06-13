"""
ParserRegistry — maps file extension / language to the right parser.
Returns None for unsupported languages; callers fall back to raw diff.
"""
from __future__ import annotations

from functools import lru_cache

from domain.services.i_code_parser import ICodeParser

# Lazy init so tests that don't need parsers don't import tree-sitter
_EXT_TO_LANG: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
}


def lang_for_path(path: str) -> str | None:
    for ext, lang in _EXT_TO_LANG.items():
        if path.endswith(ext):
            return lang
    return None


@lru_cache(maxsize=4)
def _get_parser(language: str) -> ICodeParser | None:
    try:
        if language == "python":
            from infrastructure.parsers.python_parser import PythonParser  # noqa: PLC0415
            return PythonParser()
        if language in ("javascript", "js"):
            from infrastructure.parsers.typescript_parser import JavaScriptParser  # noqa: PLC0415
            return JavaScriptParser()
        if language in ("typescript", "ts", "tsx"):
            from infrastructure.parsers.typescript_parser import TypeScriptParser  # noqa: PLC0415
            return TypeScriptParser()
    except Exception:  # noqa: BLE001
        return None
    return None


def get_parser(path: str) -> ICodeParser | None:
    lang = lang_for_path(path)
    if lang is None:
        return None
    return _get_parser(lang)
