# Live ResearchAgent Integration PRD

Status: Phase 1 through Phase 4 are implemented. Live mode prepares SEC data first, then delegates both single-company and multi-company answering to `ResearchAgent`.

## Overview

Unify live-mode answer synthesis with the existing `ResearchAgent` orchestration layer while keeping live ingestion as a separate guarded data-loading workflow.

Today, cached/default mode uses `ResearchAgent` for tiering, route selection, SQL/RAG/deep-research execution, evidence validation, retries, answer synthesis, and trace output. Live mode now resolves and refreshes company data before calling `ResearchAgent` over the prepared local store. Multi-company live comparisons reuse the precomputed research plan so the agent performs the cross-company SQL/RAG execution and validation after ingestion.

The proposed change is:

1. Resolve and refresh/load the needed company data through the existing live-ingestion pipeline.
2. After ingestion succeeds, call `ResearchAgent.run_response(question, mode="live", live=True)`.
3. Attach live-ingestion metadata to the returned `agent_trace` and response payload.

This keeps ingestion operationally safe while making cached and live answering behavior consistent.

## Problem

The architecture is now unified around one answering layer:

- Cached/default mode is `ResearchAgent`-driven.
- Live single-company mode resolves and ingests data, then answers through `ResearchAgent`.
- Live multi-company mode resolves and ingests each planned company, then answers through `ResearchAgent` using the precomputed research plan.
- MCP can request trace output; live traces include both live-ingestion metadata and the agent state.

The implementation is intended to answer these reviewer questions directly in code:

- Does live mode use the same tiering and evidence-validation behavior as cached mode?
- Are live answers and cached answers synthesized through the same control loop?
- Is `ResearchAgent` the main product architecture, or only a cached-mode layer?

The remaining decisions are now polish and ergonomics, not core architecture blockers.

## Goals

- Use `ResearchAgent` as the shared answer orchestration layer after live ingestion completes.
- Preserve the existing company resolution, freshness, cache reuse, SEC ingestion, parsing, embedding, and progress-reporting behavior.
- Preserve the current public response shape for FastAPI, Streamlit, and MCP clients.
- Attach live-ingestion metadata to `agent_trace` so live answers show both ingestion and research execution.
- Keep execution bounded by existing `ResearchAgent` budgets and validation rules.
- Improve tests so single-company live mode proves that ingestion happens before `ResearchAgent` execution.

## Non-Goals

- Do not replace the SEC live-ingestion pipeline.
- Do not make `ResearchAgent` responsible for downloading, parsing, loading, or embedding filings.
- Do not add new financial data sources.
- Do not change the source policy away from official SEC-filed data.
- Do not add arbitrary SQL execution.
- Do not redesign the Streamlit UI.
- Do not make live mode perform bulk market-wide ingestion.

## Target Users

- Users asking live questions about a company not yet loaded locally.
- Users asking live questions where local company data is stale.
- MCP clients that need a cited answer plus trace metadata.
- Recruiters or engineers reviewing whether the repo has a coherent agentic architecture.

## User Stories

1. As a user, I can ask a live single-company question and get an answer produced by the same research agent used in cached mode.
2. As a user, I can see whether live mode reused cached SEC data or refreshed it before answering.
3. As an MCP client, I can request `return_trace=True` and receive both live-ingestion metadata and `ResearchAgent` execution state.
4. As a developer, I can test that live ingestion runs before `ResearchAgent` execution.
5. As a reviewer, I can follow one answer path from API/Streamlit/MCP through `hybrid_tool.answer_question()` into `ResearchAgent`.

## Current Architecture

```text
Cached/default question
        |
        v
agent.hybrid_tool.answer_question(...)
        |
        v
answer_question_cached(...)
        |
        v
ResearchAgent.run_response(...)
        |
        v
ResearchAgent.run_state(...)
```

```text
Live single-company question
        |
        v
agent.hybrid_tool.answer_question(...)
        |
        v
answer_question_live(...)
        |
        v
resolve company -> run live ingestion -> ResearchAgent.run_response(...)
```

```text
Live multi-company question
        |
        v
answer_question_live(...)
        |
        v
answer_question_live_multi_company(...)
        |
        v
resolve companies -> run live ingestion per company -> ResearchAgent.run_response(...)
```

## Proposed Architecture

```text
Live question
        |
        v
agent.hybrid_tool.answer_question(..., live_analysis=True)
        |
        v
resolve planned companies
        |
        v
run_live_ingestion(...) for missing/stale companies
        |
        v
ResearchAgent.run_response(question, mode="live", live=True)
        |
        v
attach live_ingestion metadata to response and agent_trace
```

The live pipeline remains responsible for data readiness. The agent remains responsible for research execution over the local store.

## Functional Requirements

### 1. Live Data Preparation

Before calling `ResearchAgent`, live mode must:

- create or reuse a research plan for the question;
- resolve all planned companies through the existing company resolver;
- return the current clarification flow when company resolution is ambiguous;
- run `run_live_ingestion()` for each resolved company;
- respect freshness/cache behavior unless a future force-refresh option is added;
- preserve progress callbacks for resolve, cache, analysis, and answer stages.

### 2. ResearchAgent Invocation

After ingestion succeeds, live mode must call:

```python
ResearchAgent().run_response(question, mode="live", live=True)
```

The response should use the same top-level fields as cached mode:

- `status`
- `mode`
- `route`
- `route_reasons`
- `structured_evidence`
- `retrieved_evidence`
- `answer`
- `research_plan`
- `plan_validation`
- `agent_trace`

### 3. Live Metadata Attachment

Live mode must attach ingestion metadata without hiding the agent trace.

Top-level response fields:

- `resolved_company` or `resolved_companies`
- `live_ingestion` or `live_ingestions`

Trace fields:

- `agent_trace["live_ingestion"]`
- `agent_trace["live_ingestions"]`, when multiple companies are involved
- `agent_trace["resolved_company"]` or `agent_trace["resolved_companies"]`
- `agent_trace["live_data_ready"] = true`

### 4. Single-Company Live Behavior

Single-company live mode should no longer compose the final answer directly inside `answer_question_live()`.

Expected behavior:

1. plan the question;
2. resolve the company;
3. refresh or reuse cached data;
4. call `ResearchAgent.run_response(..., mode="live", live=True)`;
5. attach live metadata;
6. return the agent response.

### 5. Multi-Company Live Behavior

Multi-company live mode should use the same ingestion-before-agent pattern as single-company live mode.

- resolve and ingest all planned companies;
- call `ResearchAgent.run_response(..., mode="live", live=True)`;
- attach all per-company ingestion metadata.

### 6. API, Streamlit, And MCP Compatibility

The existing entrypoints must continue to work:

- `app/api.py` calls `answer_question(...)`;
- `app/ui_streamlit.py` calls `answer_question(...)`;
- `mcp_server/tools.py` calls `answer_question(..., return_trace=True)`.

No caller should need to import `ResearchAgent` directly.

### 7. Scope Guard And Refusals

Out-of-scope questions must still be refused before ingestion or tool execution.

Live mode must not refresh company data for questions that fail the public-company financial scope guard.

### 8. Failure Handling

Live mode should return structured errors for:

- unresolved company;
- ambiguous company with no clarification;
- live ingestion failure;
- agent execution failure after ingestion.

If ingestion succeeds but the agent cannot find enough evidence, the answer should use the existing evidence-warning behavior rather than inventing missing facts.

## Response Contract

Example live response shape:

```json
{
  "status": "success",
  "mode": "live",
  "route": "hybrid",
  "route_reasons": ["tier=deep_research", "live_ingest=cache_hit"],
  "structured_evidence": {"rows": []},
  "retrieved_evidence": [],
  "answer": "...",
  "research_plan": {},
  "plan_validation": {},
  "resolved_company": {},
  "live_ingestion": {
    "used_cache": true,
    "structured_counts": {},
    "document_counts": {},
    "embedding_counts": {},
    "freshness": {}
  },
  "agent_trace": {
    "mode": "live",
    "tier": "deep_research",
    "route": "hybrid",
    "companies": ["MSFT"],
    "tools_used": ["sql", "rag"],
    "retries": 0,
    "validation": {},
    "live_data_ready": true,
    "live_ingestion": {}
  }
}
```

## Implementation Plan

### Phase 1: Extract Live Preparation

Create a helper in `agent/hybrid_tool.py`:

```python
prepare_live_companies(question, clarification_response, progress_callback) -> LivePreparationResult
```

The result should include:

- status;
- research plan;
- resolved companies;
- ingestion results;
- response payload for clarification or failure states.

### Phase 2: Add Agent-Based Live Answering

Create a helper:

```python
answer_question_live_with_agent(...)
```

It should:

- call live preparation;
- call `ResearchAgent().run_response(question, mode="live", live=True)`;
- merge live metadata into the response;
- return the same public response shape.

### Phase 3: Route Single-Company Live Through Agent

Update `answer_question(..., live_analysis=True)` so single-company live requests use the new helper.

Single-company live mode should keep existing clarification and not-found behavior while using `ResearchAgent` after ingestion.

### Phase 4: Route Multi-Company Live Through Agent

After all planned companies are ingested, call `ResearchAgent` once for the original question and attach all per-company ingestion metadata.

This should replace duplicated SQL/RAG/validation logic in `answer_question_live_multi_company()`.

### Phase 5: Documentation

Update README runtime-mode note:

- cached mode uses `ResearchAgent`;
- live mode prepares data through live ingestion, then uses `ResearchAgent` for answering;
- live ingestion metadata is included in trace output.

## Testing Requirements

Add or update tests for:

1. live single-company mode calls `run_live_ingestion()` before `ResearchAgent.run_response()`;
2. live single-company mode returns `agent_trace` when `return_trace=True`;
3. live single-company mode preserves clarification behavior for ambiguous companies;
4. live out-of-scope requests do not call live ingestion;
5. live ingestion metadata is attached to the top-level response and trace;
6. multi-company live behavior either remains covered by existing tests or is migrated to agent-based execution with updated tests;
7. MCP `answer_financial_question(..., live_analysis=True)` returns trace metadata.

Run:

```powershell
python -m compileall agent app mcp_server tests
black .
ruff check . --fix
pytest
```

## Success Metrics

- Single-company live answers are produced through `ResearchAgent`.
- Cached and live answers share the same answer orchestration and trace model.
- No regression in existing live ingestion behavior.
- Existing tests pass.
- New integration tests prove the order: scope guard -> resolve -> ingest -> agent -> trace.
- README architecture description matches code.

## Risks And Mitigations

| Risk | Mitigation |
| --- | --- |
| Double planning creates inconsistent company lists | Reuse the same `ResearchPlan` where possible or pass the plan into `ResearchAgent` through an injectable planner. |
| Live ingestion succeeds but agent cannot find evidence | Preserve current validation warnings and caveat missing evidence in the final answer. |
| Streamlit progress becomes less accurate | Keep progress callbacks in live preparation and add a final agent execution progress step. |
| Multi-company live migration changes behavior too much | Preserve the existing resolution and ingestion behavior, and test that agent execution happens after all companies are prepared. |
| Trace payload grows too large | Summarize ingestion counts at top level and keep full per-company details only in `agent_trace`. |

## Open Questions

- Should `ResearchAgent.run_response()` accept a precomputed `ResearchPlan` to avoid planning twice after live preparation?
- Should live mode expose `force_refresh` through API/MCP, or keep it internal for now?
- Should `agent_trace` include full retrieved evidence, or only evidence summaries for API/MCP consumers?
- Should Streamlit show live-ingestion metadata separately from the agent trace, or only in the debug payload?
