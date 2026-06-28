# Quick Reference — Numbers, Names, and One-Liners

> Flash cards for the factual details you need to answer without hesitation.

---

## Key Numbers

| Thing | Value |
|-------|-------|
| Gemini free tier | 1,500 req/day, 10 RPM |
| Gemini model | `gemini-2.5-flash` |
| Embedding model | `gemini-embedding-001`, 768 dimensions |
| Gemini backoff | 2s → 8s → 32s (3 retries) |
| Max job attempts | 3 |
| Stale job recovery threshold | 15 minutes |
| Worker poll interval | 5 seconds |
| JWT expiry | 7 days |
| JWT algorithm | HS256 |
| RAG top-K | 5 chunks per agent |
| Max function body lines | 300 (then trimmed) |
| Small PR threshold | ≤ 50 files (full) |
| Large PR batch size | 10 files per batch |
| Test coverage gate | 75% minimum |
| Python version | ≥ 3.12 |
| pgvector dimensions | 768 |
| pgvector index type | IVFFlat, lists=100 |
| pgvector similarity | Cosine (`<=>`) |
| Max Render cold start | ~30 seconds |
| Eval golden fixtures | 30 (24 flaw + 6 clean) |
| Eval specialist phase speedup | ~3-4× faster (parallel vs sequential) |
| Category recovery tolerance | ±3 lines (same as matcher `LINE_TOLERANCE`) |

---

## Tech Stack — One-Line Descriptions

| Technology | What it does here |
|-----------|-------------------|
| **FastAPI** | Async Python web framework; routes, DI, middleware |
| **LangGraph** | StateGraph orchestrator for multi-agent pipeline |
| **Gemini 2.5 Flash** | LLM for all agent reasoning + embeddings |
| **pgvector** | Postgres extension for vector similarity search (RAG) |
| **Neon Postgres** | Serverless Postgres host (free tier) |
| **Langfuse** | LLM observability — traces, spans, token counts |
| **tree-sitter** | AST parser for Python/TS function/class extraction |
| **SQLAlchemy (async)** | ORM with asyncpg driver |
| **Alembic** | DB schema migrations |
| **pydantic v2** | Data validation, DTOs, settings management |
| **structlog** | JSON structured logging |
| **python-jose** | JWT encode/decode |
| **Upstash Redis** | (legacy) job queue — now replaced by Postgres polling |
| **Render** | Backend hosting (Docker, free tier) |
| **Vercel** | Frontend hosting (React SPA) |
| **React + Vite + TS** | Frontend framework |
| **TanStack Query** | Server-state management (caching, mutations) |
| **Zustand** | Client-state (auth token only) |
| **Tailwind + shadcn/ui** | UI styling |
| **ruff** | Python linting + formatting (replaces flake8/black/isort) |
| **mypy (strict)** | Python type checking |

---

## Architecture Layers — What's Forbidden

| Layer | Cannot import from |
|-------|--------------------|
| `domain/` | Anything outside stdlib |
| `application/` | `infrastructure/`, `fastapi`, `sqlalchemy`, `httpx` |
| `api/routes/` | `infrastructure/` directly |
| Agent nodes | DB, HTTP, Redis — pure state transformers only |

---

## Agent Pipeline — What Each Agent Does

| Agent | Primary concern |
|-------|----------------|
| **SupervisorAgent** | Reads diff metadata → chooses which specialists run |
| **SecurityAgent** | OWASP Top 10, secrets, injection, insecure patterns |
| **PerfAgent** | N+1 queries, async blocking, algorithmic complexity |
| **ArchAgent** | Layer violations, tight coupling, circular deps |
| **TestAgent** | Missing tests, weak assertions, test-to-code ratio |
| **SynthesisAgent** | Dedup, severity reconcile, overall summary |

**Execution order**: Supervisor (sequential) → Specialists (parallel via `asyncio.gather`) → Synthesis (sequential).

---

## Key Tables — Primary Purpose

| Table | Primary purpose |
|-------|----------------|
| `github_installations` | Track GitHub App installations per org/user |
| `repositories` | Repos with App installed; `is_active` toggle |
| `agent_configs` | Per-repo agent toggles + min_severity |
| `review_jobs` | Async job queue; idempotency via `UNIQUE(repo, head_sha)` |
| `reviews` | Completed review output; severity counts |
| `findings` | Individual line-level issues from agents |
| `code_embeddings` | pgvector chunks for RAG; keyed by `(repo, commit_sha)` |
| `embedding_cleanup_jobs` | Async jobs to delete embeddings on PR close |
| `eval_runs` | F-08 eval run metadata (precision/recall) |
| `eval_results` | Per-fixture eval results |

---

## Key Design Patterns

| Pattern | Where used |
|---------|-----------|
| CQRS (light) | Separate read (list/get) and write (create/update) use cases |
| Repository pattern | All DB access through interfaces; in-memory impls for tests |
| Dependency Injection | `container.py` wires everything; FastAPI `Depends()` |
| Idempotency | `UNIQUE` constraint + check-before-insert in use cases |
| Structured output | All Gemini calls use Pydantic schema enforcement |
| Pure state transformers | Agent nodes: receive `ReviewState`, return `ReviewState` |
| SELECT FOR UPDATE SKIP LOCKED | Worker job claiming without application-level locks |
| Content-hash dedup | Embeddings reused across commits if content unchanged |
| Exponential backoff | Gemini 429 (in client) + job retry (in use case) |
| HMAC constant-time compare | Webhook signature validation |

---

## Endpoint Quick Reference

| Method | Path | Returns |
|--------|------|---------|
| POST | `/api/v1/webhooks/github` | 202 Accepted |
| GET | `/api/v1/auth/github` | 302 → GitHub OAuth |
| GET | `/api/v1/auth/callback` | `AuthTokenDTO` |
| GET | `/api/v1/repos` | `list[RepoDTO]` |
| GET/PATCH | `/api/v1/repos/{id}/config` | `AgentConfigDTO` |
| GET | `/api/v1/reviews` | `PaginatedResponse[ReviewSummaryDTO]` |
| GET | `/api/v1/reviews/{id}` | `ReviewDetailDTO` |
| GET | `/api/v1/jobs/{id}` | `JobStatusDTO` |

---

## Severity Levels (ordered)

`critical` > `high` > `medium` > `low` > `info`

The `min_severity` per repo filters which findings get posted as GitHub comments.

---

## Error Code → HTTP Status

| Code | Status | When |
|------|--------|------|
| `UNAUTHORIZED` | 401 | Missing/invalid JWT or bad webhook HMAC |
| `FORBIDDEN` | 403 | Valid auth but wrong repo ownership |
| `NOT_FOUND` | 404 | Resource doesn't exist |
| `CONFLICT` | 409 | Duplicate job for same commit SHA |
| `VALIDATION_ERROR` | 422 | Pydantic validation failed |
| `RATE_LIMITED` | 429 | Gemini API rate limit |
| `INTERNAL_ERROR` | 500 | Unexpected error |
| `UPSTREAM_ERROR` | 502 | GitHub or Gemini returned unexpected error |

---

## Things That Are Intentionally Not In V1

- Multiple worker instances (horizontal scaling)
- Distributed locks or `SELECT FOR UPDATE` beyond SKIP LOCKED
- Token refresh flow (re-login on 7-day expiry)
- HttpOnly cookie JWT (localStorage used instead)
- GitLab/Bitbucket support (architecture designed for it, not implemented)
- Auto-fix PRs
- Slack/email notifications
- Fine-tuned models
- Multi-tenant org isolation (RLS)
