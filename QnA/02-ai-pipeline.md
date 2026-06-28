# AI Pipeline — LangGraph, Agents, RAG, Gemini

> Questions about the multi-agent system, LangGraph design, RAG implementation, and Gemini integration.

---

## LangGraph & Agent Architecture

**Q: Why did you use LangGraph instead of a simple sequential function call chain?**

A: LangGraph gives a typed, inspectable StateGraph where nodes are pure state transformers and edges define routing. Key benefits: (1) The SupervisorAgent can dynamically choose which specialist agents run on a given PR — a diff with only test file changes doesn't need SecurityAgent. (2) State flows explicitly through `ReviewState` TypedDict, making debugging and tracing deterministic. (3) LangGraph integrates cleanly with Langfuse for per-node spans. (4) Adding a new agent is adding one node and one edge — the graph is composable. A plain chain would require if/else routing logic scattered through the worker.

---

**Q: Explain the ReviewState object — what's in it and why is it designed that way?**

A: `ReviewState` is a TypedDict (not a class) that flows through the entire graph. It contains:
- **Input**: `pr_metadata` (PR title, SHAs, author), `context_units` (function/class bodies before/after), `raw_diff_chunks`, `rag_chunks` (per-agent top-5 semantic results)
- **Pipeline control**: `active_agents` (set by Supervisor), `findings` (accumulated list)
- **Output**: `summary`, `synthesis_complete`

It's a TypedDict because LangGraph's `StateGraph` requires it; reducers on lists (`findings`) allow nodes to append without overwriting. Agents are pure state transformers — they receive this dict and return an updated copy. No mutable class state, no DB writes inside agents, no HTTP calls. This makes agents trivially unit-testable by constructing a `ReviewState` dict and asserting on the output.

---

**Q: Why do the specialist agents run sequentially instead of in parallel?**

A: They no longer do — specialists now run in parallel via `asyncio.gather`. Here is the full story:

**The original sequential approach** was a workaround. When we first tried parallel fan-out through LangGraph nodes, `SynthesisAgent` started before all specialists had finished because LangGraph doesn't automatically wait for and merge results from parallel branches without a custom reducer on the state. Synthesis saw a half-empty `findings` list and produced incomplete reviews. Rather than add LangGraph-specific plumbing, we collapsed all specialists into one "specialists" node and looped through them — simple but slow.

**The parallel fix** is inside that same single node. Instead of a `for agent in active_agents: state = await agent(state)` loop, the node now:
1. Pre-fetches RAG chunks for all active agents at once with `asyncio.gather`
2. Runs all active specialist agents at once with `asyncio.gather`, each starting from the same state snapshot
3. After all finish, merges their findings by extracting only the new items each agent added (each agent returns `prior_findings + its_own_additions`)

This is safe because agents are pure state transformers — they read the PR context and write only their own findings. They don't need to see each other's findings during their own run; only Synthesis does.

**Latency win**: 4 agents at ~15-25 seconds each used to take 60-100 seconds sequentially. Now the whole specialist phase takes ~25 seconds (the slowest agent wins). ~3-4× faster.

**Gemini rate limit impact**: Same 6 total requests per PR review. 4 fire at the same time, but the RPM limit counts *requests per minute*, not *concurrent requests* — and a single PR review uses only 6 of the 10 RPM budget, well within limits.

---

**Q: What does the SupervisorAgent actually do and how does it decide which agents run?**

A: SupervisorAgent receives the `ReviewState` with `context_units` metadata — file paths, node names, languages, change volume. It calls Gemini with a structured prompt that returns a JSON object with a boolean for each agent type. Logic embedded in the prompt: if only test files changed → skip SecurityAgent and ArchAgent; if only CSS/config → maybe skip all except ArchAgent; if it's a new feature with DB access → run all. The output is a set of `AgentType` enums stored in `state.active_agents`. If Gemini returns an invalid response, the fallback runs all four agents. This is a "soft" optimization — wrong supervisor decisions are recoverable.

---

**Q: What does SynthesisAgent do and why is it a separate agent rather than post-processing?**

A: SynthesisAgent receives all findings from all specialist agents and does three things:
1. **Deduplication**: Multiple agents can flag the same line (e.g., SecurityAgent and ArchAgent both flag a DB call in a route handler). Synthesis merges overlapping findings by file/line range and conflicting severity.
2. **Severity reconciliation**: SecurityAgent might call something "High"; ArchAgent might call the same thing "Medium". Synthesis applies a final severity judgment using the full context.
3. **Summary generation**: Produces the overall PR review body text.

It's a separate agent because these decisions require understanding all findings together — they can't be done with a simple Python dedup function because the agent needs to reason about whether two textually different findings are semantically the same issue.

---

**Q: What is the "synthesis quality gate" and why was it added?**

A: Without a quality gate, SynthesisAgent was surfacing every finding that came in from any specialist, including speculative ones like "this code *might* have an issue if…". In practice, this meant every clean PR (one with no real problems) was still getting flagged with 5-10 ghost findings. That's a terrible user experience — developers stop trusting the tool.

The quality gate is a set of rules added to SynthesisAgent's instructions:

- A finding must point to a **specific file and line number** in the changed code. If the agent can't cite exactly where the problem is, the finding is dropped.
- A finding must be in code that **actually changed** in this PR — not in surrounding context that happened to be included.
- Apply the "senior engineer" test: would a senior engineer reading this PR agree this genuinely needs attention? If the answer is "maybe" or "probably not", drop it.
- Prefer 3-5 high-confidence findings over 10+ speculative ones.
- If nothing survives these checks, return an empty list and say the code looks clean.

Think of it as a spam filter for code review comments. Without it, the system was like a reviewer who flags everything just to look thorough.

---

**Q: What was the "category recovery" bug in SynthesisAgent, how did it cause low recall, and how was it fixed?**

A: This is a subtle but important bug. Understanding it requires knowing that each finding has a `category` field — either `security`, `perf`, `arch`, or `test` — that tells the system which type of issue it is.

**What happened**: When two specialist agents flagged the same code line, synthesis merged them into one finding. SecurityAgent might call it a "security concern" and ArchAgent might call it an "architecture violation". When synthesis merged them, it kept the **security** category — because SecurityAgent's description often sounded more urgent. The problem: the eval system (and the GitHub comment output) only matched a finding as correct if the category was right. An arch finding mislabelled as "security" was counted as a missed arch issue.

**How bad was it**: Running 3 architecture fixtures before the fix showed arch recall of 0.33 — only 2 out of 6 planted arch issues found. After the fix: recall 1.00 — all 6 found. The agent was finding the right issues all along; synthesis was just relabelling them.

**The fix has two layers**:

1. **Prompt instruction**: The synthesis prompt now explicitly says: "preserve the `category` field exactly as assigned by the specialist agent that produced the finding. If two agents flagged the same location under different categories, keep the more specific specialist's category — arch/perf/test beats the catch-all security."

2. **Code-level safety net**: After synthesis runs, a `_recover_category()` function scans each output finding. If synthesis still marked something as "security", it checks whether any input finding at the same file and line range had a specific category (arch/perf/test). If so, it overrides the category back to the specialist's label. This handles cases where the LLM ignores the prompt instruction.

Think of it like a manager (synthesis) incorrectly crediting a sales win to the wrong team. The prompt says "give credit to the right person", and the code-level check is the HR system that double-checks if the wrong team got the bonus.

---

**Q: How do you enforce structured output from Gemini? What happens if it doesn't comply?**

A: All Gemini calls use `response_mime_type="application/json"` plus a Pydantic model schema passed to the API. `GeminiClient.generate()` takes a `schema: type[BaseModel]` parameter, converts it to a JSON schema (with some cleaning for Gemini compatibility — removing `$defs`, flattening nested schemas), and enforces it at the API level. Gemini's structured output mode means the model constrains its token sampling to match the schema — it cannot produce malformed JSON. If the Pydantic validation still fails (schema mismatch), the exception propagates up through the agent to the worker, which retries the job.

---

**Q: What is the Review Package and why was it designed?**

A: Instead of passing raw `+/-` diff lines to agents, the system assembles a structured Review Package first. It contains:
- **PR metadata**: title, author, SHAs, changed file list
- **Context units**: full function/class bodies (old and new versions) for every function that contains ≥1 changed line, extracted by tree-sitter AST parsing
- **RAG chunks**: top-5 semantically similar code chunks from pgvector, per agent

The rationale: a `+3 lines` diff snippet gives no information about the function signature, what it calls, or what calls it. Agents reviewing full function bodies + cross-file context produce significantly fewer false positives. The Review Package is assembled once before any agent runs; RAG queries are done per-agent with domain-specific query strings (SecurityAgent queries for "authentication authorization input validation patterns", etc.).

---

**Q: Explain how tree-sitter is used and why it's better than splitting on line counts.**

A: tree-sitter produces a full AST for Python and TypeScript/JavaScript. The parsers walk the AST to extract function and class node boundaries (start line, end line, name). When assembling the Review Package, for each changed file the system: (1) finds which AST nodes contain ≥1 changed line by line-range intersection; (2) fetches the full source of those nodes at both base SHA and head SHA from GitHub; (3) builds a `ContextUnit` with `body_old`, `body_new`, and the diff patch for that unit.

Why better than character/line-count chunking: a 600-line file split at line 300 could cut a function in half, giving agents half a function with no signature. AST-based chunking guarantees each chunk is a complete, syntactically meaningful unit. Agents reason about complete code structures.

---

**Q: How does the RAG system work? What gets embedded, when, and how is retrieval done?**

A: **What gets embedded**: Every function and class body from changed files, at the new (head) SHA. Stored in `code_embeddings` table with `(repository_id, commit_sha, file_path, chunk_index)` as dedup keys.

**When**: During `AssembleReviewPackageUseCase`, after tree-sitter parsing but before agents run. A `content_hash` column on embeddings allows reuse — if the same function body appears in a later commit unchanged, it reuses the existing embedding.

**How retrieval works**: Before each specialist agent runs, `LanggraphOrchestrator` queries `PgvectorStore.retrieve_similar()` with an agent-specific query string using cosine distance (`<=>` operator in pgvector). Each agent gets its own domain-focused query:
- SecurityAgent: "authentication authorization input validation secrets"
- PerfAgent: "database query loop N+1 async blocking"
- ArchAgent: "import dependency layer class hierarchy"
- TestAgent: "test coverage assertion mock fixture"

Top-5 results are stored in `state.rag_chunks[agent_type]` and included in that agent's prompt as cross-file context.

---

**Q: How does the Gemini client handle rate limiting?**

A: `GeminiClient` wraps the Google GenAI SDK. On a 429 `ResourceExhausted` response, it retries with exponential backoff: 2 seconds, 8 seconds, 32 seconds (3 retries total). After 3 failures it raises `ExternalServiceError`, which propagates to the worker use case, which marks the job `failed` and schedules `retry_after` for the next job-level retry attempt (up to 3 job attempts). The Gemini free tier allows 1,500 requests/day and 10 RPM; sequential agents naturally stay under RPM, and the daily limit is monitored via Langfuse token tracking.

---

**Q: How did you choose Gemini 2.5 Flash over GPT-4o or Claude?**

A: Primary factor was the free tier: Gemini 2.5 Flash offers 1,500 requests/day, 10 RPM, and a 1M token context window at no cost. For a side project needing to process full function bodies + RAG context per agent call, the large context window mattered. GPT-4o free tier (via OpenAI) has lower rate limits; Claude's API has no free tier. Gemini's structured output mode (JSON schema enforcement) was also a requirement — without it, parsing agent responses becomes fragile. The `google-genai` SDK (not the deprecated `google-generativeai`) was used because it supports the newer API surface including the `gemini-embedding-001` model at 768 dimensions.

---

**Q: What is Langfuse and why did you use it over LangSmith?**

A: Langfuse is an open-source LLM observability platform (self-hostable or cloud). Key reasons over LangSmith: (1) Langfuse has a more generous free tier for cloud hosting; (2) it integrates with LangGraph through the `@trace_agent` decorator pattern without requiring a LangChain-specific tracer; (3) it supports datasets and LLM-as-judge scoring natively, which the F-08 eval system uses. LangSmith is tighter-coupled to LangChain's SDK. The `LangfuseClient` in the project wraps the Langfuse SDK with a `NoOpClient` fallback when `LANGFUSE_SECRET_KEY` is not set, so the system works without it in development.

---

**Q: How does the eval system (F-08) work without calling the real GitHub API?**

A: The eval harness uses synthetic "golden PR" JSON fixtures. Each fixture has `context_units` (pre-built function body objects mimicking what tree-sitter + GitHub fetching would produce) and `expected_findings` (what a correct agent should find, with category, severity, file, and a `rationale` string). `EvalHarness.run_fixture()` builds a `ReviewState` directly from the fixture (bypassing GitHub and embedding) and calls the real LangGraph pipeline with real Gemini calls. `EvalMatcher` compares actual findings to expected using: (1) rule-based matching on file + category + severity; (2) optional LLM-as-judge for fuzzy semantic matching. `EvalScorer` computes precision/recall per category. Results are stored in `eval_runs`/`eval_results` tables and printed to console.

---

**Q: What is precision and recall in the context of this PR reviewer, in plain English?**

A: Imagine you have a bag of 10 bugs deliberately planted in a PR. Your review tool finds 8 things and calls them bugs.

- **Recall** = "Of the 10 real bugs, how many did I find?" If 6 of your 8 findings were real planted bugs, recall = 6/10 = 60%. High recall means you miss fewer real issues.
- **Precision** = "Of the 8 things I flagged, how many were actually real bugs?" If 6 of your 8 findings were real, precision = 6/8 = 75%. High recall means fewer false alarms.
- **F1** = the single combined score. It's the harmonic mean of precision and recall — it punishes you equally for missing things (low recall) and crying wolf (low precision).
- **False positive rate on clean PRs** = "When the PR has no bugs at all, how often does the tool still flag something?" Ideally this is 0%. Before the quality gate it was 100% — every clean PR got at least one ghost finding.

The tension: making the tool more sensitive (to catch more bugs) tends to increase false alarms. Making it more conservative (fewer false alarms) means missing real bugs. The goal is to tune both together.

---

**Q: What was the baseline eval result and what specifically improved it?**

A: **Baseline** (before this session's improvements):

| Category | Recall | Precision | F1 |
|---|---|---|---|
| security | 0.80 | 1.00 | 0.89 |
| perf | 0.58 | 1.00 | 0.74 |
| arch | 0.42 | 1.00 | 0.59 |
| test | 0.73 | 1.00 | 0.84 |
| **overall** | **0.64** | **1.00** | **0.78** |

Clean PR false-positive rate: **1.00** (100% of clean PRs were flagged with ghost findings)

There were also two hidden bugs: (1) precision was shown as 1.00 but was actually inflated — the scorer was silently dropping FP counts when the LLM returned a capitalised category like "Security" instead of "security"; (2) the JSON artifact only showed finding counts per PR, not what was missed or why.

**What was improved and why each change mattered:**

| Fix | Problem it solved |
|---|---|
| **Scorer FP normalisation** | `pred.category` was not lowercased before the bucket lookup, so "Security" ≠ "security" and FP counts silently dropped to 0 — precision was being reported as 1.00 when it wasn't |
| **Synthesis quality gate** | Agents were surfacing speculative findings on clean code; the quality gate requires a citable line range and a confident judgment before a finding survives to output |
| **Synthesis category recovery** | Synthesis was relabelling arch/perf/test findings as "security" during deduplication; this made the arch agent look like it had 0% recall even when it found the right issues — the code-level `_recover_category()` override restored the correct specialist label |
| **Strengthened arch prompt** | Vague "look for layer violations" replaced with 4 concrete violation classes and explicit instruction to scan import statements first — the place where most arch violations are immediately visible |
| **Strengthened perf prompt** | Added specific stdlib calls to flag (time.sleep, requests.get, open()) and N+1 ORM patterns with examples instead of generic descriptions |
| **Enriched eval JSON artifact** | Added `missed_findings` and `spurious_findings` with full content to `latest.json` — you can now read exactly what was missed and why without re-running |
| **Eval DB FK fix** | `eval_results` rows were being inserted before the parent `eval_runs` row was flushed, causing a FK constraint error; fixed with `session.flush()` |

The category recovery fix alone moved arch recall from 0.33 to 1.00 on the 3-fixture smoke test. The quality gate reduced clean PR noise significantly.

---
