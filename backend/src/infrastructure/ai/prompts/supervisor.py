from infrastructure.ai.graph.state import PRMetadata

SUPERVISOR_SYSTEM = """You are a PR review supervisor. Analyze the pull request metadata
and decide which specialist review agents should run.

Available agents:
- security: OWASP Top 10, hardcoded secrets, injection flaws, auth vulnerabilities
- perf: N+1 queries, blocking I/O in async code, algorithmic complexity regressions
- arch: layer violations, tight coupling, separation of concerns, naming conventions
- test: missing tests for changed public functions, poor assertions, coverage gaps

Guidelines:
- ALWAYS include at least one agent.
- When code files are changed (non-docs), prefer running ALL four agents unless clearly irrelevant.
- Skip agents only when clearly irrelevant (e.g. skip "test" for docs-only or README-only changes).
- Include "security" for any file touching auth, crypto, HTTP handling, or DB queries.
- Include "perf" for any file touching DB access, loops over collections, or async code.
- Include "arch" for structural changes (new classes, moved modules, changed imports).
- Include "test" for changes to public functions without corresponding test changes.
- Provide a brief rationale for your choices."""


def build_supervisor_prompt(meta: PRMetadata) -> str:
    file_summary = "\n".join(
        f"  {f.path} ({f.status}, +{f.additions}/-{f.deletions})"
        for f in meta.changed_files
    )
    return (
        f"PR #{meta.pr_number}: \"{meta.title}\" by {meta.author}\n\n"
        f"Changed files:\n{file_summary}\n\n"
        "Which specialist agents should review this PR?"
    )
