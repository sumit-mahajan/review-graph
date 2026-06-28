"""Shared utilities for building agent prompts."""

from infrastructure.ai.graph.state import ContextUnit, PRMetadata, RawDiffChunk


def format_pr_header(meta: PRMetadata) -> str:
    files = ", ".join(f.path for f in meta.changed_files[:10])
    if len(meta.changed_files) > 10:
        files += f" (+{len(meta.changed_files) - 10} more)"
    return (
        f'PR #{meta.pr_number}: "{meta.title}" by {meta.author}\n'
        f"Base: {meta.base_branch} ({meta.base_sha[:8]}) → "
        f"Head: {meta.head_branch} ({meta.head_sha[:8]})\n"
        f"Changed files: {files}\n"
    )


def format_context_units(units: list[ContextUnit], max_units: int = 8) -> str:
    if not units:
        return ""
    parts: list[str] = []
    for unit in units[:max_units]:
        parts.append(
            f"\n=== {unit.node_type}: {unit.file_path}::{unit.node_name} "
            f"(lines {unit.start_line}–{unit.end_line}, {unit.language}) ===\n"
            f"--- OLD ---\n{unit.body_old or '(new file)'}\n"
            f"--- NEW ---\n{unit.body_new}\n"
            f"--- DIFF ---\n{unit.diff_patch}\n"
        )
    if len(units) > max_units:
        parts.append(f"\n... ({len(units) - max_units} more context units omitted)\n")
    return "\n".join(parts)


def format_raw_diffs(chunks: list[RawDiffChunk], max_chunks: int = 15) -> str:
    if not chunks:
        return ""
    parts: list[str] = []
    for chunk in chunks[:max_chunks]:
        parts.append(f"\n=== {chunk.file_path} ({chunk.language}) ===\n{chunk.patch}\n")
    return "\n".join(parts)


def format_rag_context(rag_chunks: list[str], label: str) -> str:
    if not rag_chunks:
        return ""
    joined = "\n\n".join(rag_chunks[:5])
    return f"\n=== RELATED {label.upper()} CONTEXT (retrieved) ===\n{joined}\n"
