"""Tests for diff_utils."""

from domain.services.i_pr_fetcher import FilePatch
from domain.utils.diff_utils import (
    build_diff_line_index,
    extract_changed_lines,
    is_comment_on_diff,
)


def test_extract_changed_lines_counts_plus_lines() -> None:
    patch = """@@ -1,3 +1,4 @@
 line1
-old
+new
+added
"""
    assert extract_changed_lines(patch) == {2, 3}


def test_build_diff_line_index_maps_paths() -> None:
    patches = [
        FilePatch(
            path="a.py",
            status="modified",
            patch="@@ -1 +1 @@\n+x",
            additions=1,
            deletions=0,
        ),
        FilePatch(path="b.py", status="added", patch="", additions=0, deletions=0),
    ]
    index = build_diff_line_index(patches)
    assert "a.py" in index
    assert "b.py" not in index


def test_is_comment_on_diff_requires_all_lines_in_range() -> None:
    diff_lines = {"src/a.py": {10, 11, 12}}
    assert is_comment_on_diff(file_path="src/a.py", line=10, line_end=11, diff_lines=diff_lines)
    assert not is_comment_on_diff(file_path="src/a.py", line=10, line_end=15, diff_lines=diff_lines)
    assert not is_comment_on_diff(
        file_path="other.py", line=10, line_end=None, diff_lines=diff_lines
    )
