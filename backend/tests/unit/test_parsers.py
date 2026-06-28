"""Tests for tree-sitter Python and TypeScript parsers."""

from infrastructure.parsers.parser_registry import get_parser, lang_for_path
from infrastructure.parsers.python_parser import PythonParser
from infrastructure.parsers.typescript_parser import TypeScriptParser
from tests.fixtures.python_sample import PYTHON_SOURCE, TYPESCRIPT_SOURCE


def test_python_parser_extracts_function() -> None:
    parser = PythonParser()
    nodes = parser.parse(PYTHON_SOURCE)

    names = {n.node_name for n in nodes}
    assert "authenticate_user" in names
    assert "get_user" in names
    assert "create_user" in names


def test_python_parser_extracts_class() -> None:
    parser = PythonParser()
    nodes = parser.parse(PYTHON_SOURCE)
    class_nodes = [n for n in nodes if n.node_type == "class"]
    assert any(n.node_name == "UserService" for n in class_nodes)


def test_python_parser_records_line_numbers() -> None:
    parser = PythonParser()
    nodes = parser.parse(PYTHON_SOURCE)
    auth_fn = next(n for n in nodes if n.node_name == "authenticate_user")
    assert auth_fn.start_line == 1
    assert auth_fn.end_line >= 7


def test_python_parser_body_matches_source() -> None:
    parser = PythonParser()
    nodes = parser.parse(PYTHON_SOURCE)
    auth_fn = next(n for n in nodes if n.node_name == "authenticate_user")
    assert "hash_password" in auth_fn.body


def test_typescript_parser_extracts_function() -> None:
    parser = TypeScriptParser()
    nodes = parser.parse(TYPESCRIPT_SOURCE)
    names = {n.node_name for n in nodes}
    assert "fetchUser" in names


def test_typescript_parser_extracts_class() -> None:
    parser = TypeScriptParser()
    nodes = parser.parse(TYPESCRIPT_SOURCE)
    class_nodes = [n for n in nodes if n.node_type == "class"]
    assert any(n.node_name == "AuthService" for n in class_nodes)


def test_python_parser_supports_language() -> None:
    parser = PythonParser()
    assert parser.supports("python") is True
    assert parser.supports("typescript") is False


def test_typescript_parser_supports_language() -> None:
    parser = TypeScriptParser()
    assert parser.supports("typescript") is True
    assert parser.supports("python") is False


def test_parser_registry_returns_python_for_py_extension() -> None:
    parser = get_parser("src/auth/handlers.py")
    assert parser is not None
    assert parser.supports("python") is True


def test_parser_registry_returns_ts_for_ts_extension() -> None:
    parser = get_parser("src/components/Auth.tsx")
    assert parser is not None


def test_parser_registry_returns_none_for_unsupported() -> None:
    assert get_parser("src/main.java") is None
    assert get_parser("README.md") is None


def test_lang_for_path_mapping() -> None:
    assert lang_for_path("foo.py") == "python"
    assert lang_for_path("foo.ts") == "typescript"
    assert lang_for_path("foo.tsx") == "typescript"
    assert lang_for_path("foo.js") == "javascript"
    assert lang_for_path("foo.go") is None
