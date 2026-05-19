# MCP Server PRD

## Overview

Add a Model Context Protocol (MCP) server that exposes the Public Company Research Assistant's SEC/XBRL research capabilities as governed tools, resources, and prompts for MCP-compatible clients.

The goal is to turn the project from a single app that internally routes SQL/RAG work into a reusable financial research tool layer that external agents can call safely.

## Problem

Today, the Streamlit/FastAPI app owns the full interaction loop:

- interpret the user question
- route to SQL, RAG, hybrid, or live ingestion
- query Postgres / `pgvector`
- validate evidence
- synthesize the final answer

That works for the app, but the capabilities are not directly reusable by other AI clients. A recruiter, agent framework, or MCP-compatible desktop client cannot independently call the financial tools without going through the app-specific API/UI flow.

## Goals

- Expose core financial research capabilities through MCP tools.
- Keep database and ingestion access governed, typed, and auditable.
- Support SEC-grounded metric lookup, filing retrieval, company refresh, and cited answer generation.
- Preserve existing app behavior; MCP should be an additional interface, not a replacement.
- Make the project demonstrate modern agent architecture: LLM + tools + retrieval + state + validation + controlled execution.

## Non-Goals

- Do not expose arbitrary SQL execution.
- Do not add non-SEC data sources in this feature.
- Do not build a new frontend.
- Do not replace the existing FastAPI or Streamlit app.
- Do not make write operations available except controlled company refresh/ingestion.
- Do not implement portfolio advice, price targets, trading recommendations, or investment advice.

## Target Users

- MCP-compatible AI clients that need financial research tools.
- Developers evaluating the project as an AI engineering portfolio artifact.
- Internal agents that need governed access to SEC filings and structured metrics.

## User Stories

1. As an MCP client, I can query a company's financial metrics without generating SQL.
2. As an MCP client, I can retrieve filing passages about a topic with citation metadata.
3. As an MCP client, I can refresh a company from official SEC sources when local data is stale or missing.
4. As an MCP client, I can compare metrics across multiple companies over a bounded period.
5. As an MCP client, I can ask a public-company finance question and receive a cited answer grounded in SQL/RAG evidence.
6. As a developer, I can inspect logs to see which tools were called and whether validation passed.

## Proposed MCP Tools

### `query_financial_metrics`

Returns structured metrics from `v_company_period_metrics`.

Inputs:

- `ticker`: string
- `metrics`: list of allowed metric names
- `periods`: optional period selector such as `latest`, `last_four_quarters`, or explicit dates
- `fiscal_quarter_only`: boolean, default `true`

Outputs:

- normalized rows
- source labels for citations
- warnings for missing metrics or missing periods

Guardrails:

- parameterized queries only
- allowed metrics whitelist
- row limit
- no arbitrary SQL

### `retrieve_filing_context`

Retrieves filing chunks from SEC documents.

Inputs:

- `ticker`: string
- `topic`: string
- `filing_types`: optional list such as `10-K`, `10-Q`, `8-K`, `8-K EX-99.1`
- `limit`: integer with a bounded maximum

Outputs:

- chunks
- scores
- citation metadata
- source URLs

Guardrails:

- ticker-scoped retrieval by default
- bounded `limit`
- return no unrelated-company evidence

### `refresh_company_data`

Runs controlled live ingestion for a validated US public-company ticker.

Inputs:

- `ticker`: string
- `required_sources`: `structured`, `unstructured`, or both
- `force_refresh`: boolean, default `false`

Outputs:

- resolved company
- cache status
- structured counts
- document counts
- embedding counts
- freshness metadata

Guardrails:

- validate ticker through existing resolver
- respect SEC user-agent requirements
- reuse freshness cache unless `force_refresh` is true
- bounded ingestion scope

### `compare_company_metrics`

Returns side-by-side metric rows for multiple tickers.

Inputs:

- `tickers`: list of strings
- `metrics`: list of allowed metric names
- `periods`: selector such as `latest`, `last_four_quarters`, or explicit dates

Outputs:

- rows grouped by ticker
- missing-data warnings
- citation labels

Guardrails:

- max ticker count
- allowed metrics whitelist
- read-only queries only

### `answer_financial_question`

Runs the existing research agent and returns a citation-backed answer.

Inputs:

- `question`: string
- `live_analysis`: boolean, default `false`

Outputs:

- answer markdown
- route
- research plan
- structured evidence summary
- retrieved evidence summary
- validation warnings

Guardrails:

- scope classifier must pass
- no answer from unrelated evidence
- cite all evidence used
- return structured refusal for out-of-scope requests

## Proposed MCP Resources

### `companies://loaded`

Returns companies currently present in the local store.

### `metrics://schema`

Returns allowed structured metrics and human-readable descriptions.

### `sources://sec-policy`

Returns the current source policy and supported SEC filing types.

### `freshness://companies`

Returns freshness metadata per company.

### `agent://capabilities`

Returns supported routes, tools, limits, and known limitations.

## Proposed MCP Prompts

### `public_company_research_question`

Guides an MCP client to ask in-scope public-company financial/filing questions.

### `compare_companies`

Template for multi-company metric + narrative comparison.

### `forecast_with_evidence_limits`

Template that asks for a forecast only when company guidance, filings, or structured metrics support it, and otherwise returns a missing-evidence explanation.

## Architecture

```text
MCP-compatible client
        |
        v
MCP server
        |
        v
Governed tools
  - metric query
  - filing retrieval
  - live refresh
  - comparison
  - cited answer
        |
        v
Existing backend
  - ResearchAgent
  - SQL tool
  - RAG tool
  - live ingestion
  - Postgres / pgvector
```

The MCP server should call existing internal modules instead of duplicating logic.

## Data And Safety Requirements

- Use official SEC/XBRL and SEC-filed document data only.
- Do not expose raw arbitrary SQL execution.
- Do not expose database credentials through MCP responses.
- Validate tickers before refresh.
- Enforce max rows, max chunks, max companies, and timeout limits.
- Return structured errors for missing evidence or out-of-scope questions.
- Maintain source URLs and citation metadata in outputs.

## Observability Requirements

Each MCP tool call should log:

- tool name
- timestamp
- sanitized inputs
- resolved ticker/company
- route used
- SQL row count
- retrieval count
- validation warnings
- latency
- error state

Logs should not include API keys, database credentials, or raw secrets.

## Testing Requirements

Unit tests:

- tool input validation
- metric whitelist enforcement
- ticker-scoped retrieval
- no unrelated-company evidence
- out-of-scope refusal
- no arbitrary SQL execution

Integration tests:

- `query_financial_metrics` returns expected rows for a loaded company
- `retrieve_filing_context` returns citation metadata
- `answer_financial_question` returns answer + research plan + evidence
- missing-company cached mode returns structured evidence-gap response

Smoke tests:

- MCP server starts
- tool list is exposed
- resources list is exposed
- sample MCP client can call at least one tool

## Acceptance Criteria

- MCP server exposes the MVP tools and resources.
- Tools call existing backend modules rather than duplicating business logic.
- All tools return typed, JSON-serializable responses.
- SQL access is read-only and parameterized.
- Retrieval is company-scoped when ticker is supplied.
- Out-of-scope questions are refused before tool execution.
- Existing Streamlit/FastAPI behavior remains unchanged.
- Tests pass locally and in CI.
- README documents MCP as an implemented optional interface only after this feature is complete.

## Rollout Plan

### Phase 1: MCP Skeleton

- Add MCP server entrypoint.
- Expose health/capability resource.
- Add smoke test.

### Phase 2: Read-Only Tools

- Implement `query_financial_metrics`.
- Implement `retrieve_filing_context`.
- Add validation and tests.

### Phase 3: Live Refresh Tool

- Implement `refresh_company_data`.
- Reuse existing resolver and live ingestion.
- Add freshness and bounded-refresh tests.

### Phase 4: Agent Tool

- Implement `answer_financial_question`.
- Return research plan, route, warnings, and final answer.
- Add out-of-scope and missing-evidence tests.

### Phase 5: Docs And Demo

- Add README MCP section.
- Add sample MCP client config.
- Add example calls.

## Open Questions

- Which MCP Python server library should be used?
- Should the MCP server run as a separate process or inside the existing API container?
- Should live refresh be enabled by default for MCP clients, or require an explicit configuration flag?
- What limits should be used for max companies, rows, chunks, and refresh frequency?
- Should MCP logs write to stdout, a file, or a database table?
