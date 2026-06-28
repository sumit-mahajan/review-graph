"""Helpers for parsing unified diff patches."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.services.i_pr_fetcher import FilePatch


def extract_changed_lines(patch: str) -> set[int]:
    """Return new-file line numbers touched by a unified diff patch."""
    changed: set[int] = set()
    current_line = 0
    for line in patch.splitlines():
        hunk = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
        if hunk:
            current_line = int(hunk.group(1)) - 1
            continue
        if line.startswith("-") or line.startswith("\\"):
            continue
        current_line += 1
        if line.startswith("+"):
            changed.add(current_line)
    return changed


def build_diff_line_index(file_patches: list[FilePatch]) -> dict[str, set[int]]:
    """Map file path → changed line numbers on the RIGHT (head) side."""
    index: dict[str, set[int]] = {}
    for patch in file_patches:
        if not patch.patch:
            continue
        index[patch.path] = extract_changed_lines(patch.patch)
    return index


def is_comment_on_diff(
    *,
    file_path: str,
    line: int,
    line_end: int | None,
    diff_lines: dict[str, set[int]],
) -> bool:
    """True when the comment target lies on changed lines in the PR diff."""
    lines = diff_lines.get(file_path)
    if not lines or line < 1:
        return False
    end = line_end if line_end is not None else line
    if end < line:
        end = line
    return all(ln in lines for ln in range(line, end + 1))
