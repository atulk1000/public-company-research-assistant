# Research Planning Layer Requirements

## Goal

Add a planning layer that turns each user question into a structured research plan before route, tier, and tool decisions are finalized.

The planning layer should make the agent reason about what it needs to learn, what evidence is required, and how success will be validated. SQL, RAG, hybrid routing, retries, answer synthesis, and final formatting should then execute against that plan.

## Product Outcome

The assistant should feel less like a router and more like a bounded research analyst. For a question such as:

```text
Compare Microsoft and Alphabet on AI narrative and capex intensity over the last four quarters.
```

The agent should create an explicit plan similar to:

1. Identify companies: Microsoft (`MSFT`) and Alphabet (`GOOGL`).
2. Pull last four quarterly capex/revenue and R&D/revenue metrics for both companies.
3. Retrieve Microsoft filing passages about AI infrastructure, Copilot, Azure AI, and OpenAI exposure.
4. Retrieve Alphabet filing passages about Gemini, AI infrastructure, Google Cloud AI, and AI-related investments.
5. Compare capex intensity, R&D intensity, revenue context, and AI narrative.
6. Validate that both companies have SQL and document evidence.
7. Call out missing quarter data or missing narrative evidence before synthesis.

## Non-Goals

- Do not add open-web browsing.
- Do not add third-party financial data sources.
- Do not let the agent run unbounded loops.
- Do not allow arbitrary SQL tables beyond the approved metrics view.
- Do not remove the current SQL/RAG/hybrid routes; the planning layer should orchestrate them.

## Core Requirements

### 1. Research Plan Object

Create a structured `ResearchPlan` object that can be serialized into the API response trace.

Required fields:

- `question`: original user question.
- `companies`: list of planned company tickers.
- `comparison`: boolean indicating whether the user is asking for comparison.
- `time_window`: normalized time scope when detectable, such as `last_four_quarters`, `latest_quarter`, `last_two_years`, or `unspecified`.
- `required_metrics`: list of metric names needed from SQL.
- `document_themes`: list of document themes or search concepts needed from filings.
- `required_sources`: list containing `structured`, `unstructured`, or both.
- `evidence_requirements`: explicit coverage expectations.
- `validation_checks`: checks that must pass or produce caveats.
- `planned_steps`: ordered list of steps the agent intends to execute.
- `route_hint`: initial route hint: `sql`, `rag`, or `hybrid`.
- `tier_hint`: initial tier hint: `sql_fast`, `rag_fast`, `hybrid_fast`, or `deep_research`.
- `rationale`: short explanation of why the plan was chosen.

Example:

```json
{
  "question": "Compare Microsoft and Alphabet on AI narrative and capex intensity over the last four quarters.",
  "companies": ["MSFT", "GOOGL"],
  "comparison": true,
  "time_window": "last_four_quarters",
  "required_metrics": ["capex_pct_revenue", "rd_pct_revenue", "revenue_growth_yoy"],
  "document_themes": ["AI infrastructure", "Copilot", "Azure AI", "Gemini", "Google Cloud AI", "AI investment"],
  "required_sources": ["structured", "unstructured"],
  "evidence_requirements": {
    "sql_companies": ["MSFT", "GOOGL"],
    "rag_companies": ["MSFT", "GOOGL"],
    "minimum_quarters_per_company": 4
  },
  "validation_checks": [
    "both companies have SQL rows",
    "both companies have document evidence",
    "four-quarter metric coverage is complete or caveated",
    "answer separates facts from inference"
  ],
  "planned_steps": [
    "resolve companies",
    "query last four quarters of capex and R&D intensity",
    "retrieve AI narrative evidence for each company",
    "validate evidence coverage",
    "synthesize and format final answer"
  ],
  "route_hint": "hybrid",
  "tier_hint": "deep_research",
  "rationale": "The question asks for a multi-company comparison combining metrics and filing narrative."
}
```

### 2. Plan Generation

The agent should generate a plan before deciding final execution.

Inputs:

- user question
- loaded company catalog
- extracted companies from the existing ticker/company resolver
- route classifier output, if available
- known metric vocabulary
- known document theme vocabulary

The planner may use an LLM, but it must return a validated structured object. If the LLM planner fails, the system should fall back to deterministic planning from existing tier and route heuristics.

### 3. Route, Tier, and Tool Decisions From Plan

Route and tier decisions should be derived from the plan:

- `required_sources = ["structured"]` implies SQL route.
- `required_sources = ["unstructured"]` implies RAG route.
- both sources imply hybrid route.
- multi-company comparisons, ambiguous questions, missing evidence risk, or multiple document themes should favor `deep_research`.
- simple single-company metric plans should favor `sql_fast`.
- simple single-company narrative plans should favor `rag_fast`.

The existing `decide_tier` behavior can remain as a fallback, but the plan should become the primary execution contract.

### 4. Plan-Aware SQL Execution

For structured needs, the agent should pass plan context into SQL generation:

- required companies
- required metrics
- time window
- comparison intent

For `last_four_quarters`, SQL generation should request four quarterly rows per company where possible.

The SQL result should be tagged against plan requirements:

- companies found
- metrics returned
- quarters returned per company
- missing metric values

### 5. Plan-Aware Retrieval Execution

For document needs, retrieval should run per company and per theme when appropriate.

Example for the AI narrative comparison:

- `MSFT`: AI infrastructure, Copilot, Azure AI, OpenAI
- `GOOGL`: Gemini, Google Cloud AI, AI infrastructure, AI investment

Retrieval should preserve company balance so one company cannot dominate the answer context.

Minimum behavior:

- retrieve at least one company-scoped evidence set per planned company when unstructured evidence is required.
- cap per-company evidence to keep answer synthesis focused.
- retry missing or weak company evidence using expanded terms.

### 6. Evidence Validation

Validation should compare actual evidence against the plan, not only against route/tier.

Required validation outputs:

- `passed`: boolean.
- `missing_sql_companies`: company tickers missing from SQL results.
- `missing_rag_companies`: company tickers missing from document results.
- `missing_metrics`: required metrics absent from SQL results.
- `missing_periods`: expected time periods or quarter counts not present.
- `weak_document_themes`: document themes with poor or missing retrieval.
- `warnings`: user-facing caveats to feed into answer synthesis.
- `needs_retry`: boolean.

Validation examples:

- If Alphabet has two quarters with null capex, validation should add a warning.
- If Microsoft has document evidence but Alphabet does not, validation should trigger a RAG retry for Alphabet themes.
- If a required metric is not available, the final answer must caveat that limitation.

### 7. Plan Revision And Retry

The agent should revise weak execution steps within fixed budgets.

Allowed revisions:

- expand retrieval terms for missing document themes.
- retry retrieval for companies missing RAG evidence.
- relax a document theme from specific to broader language, such as `Gemini` to `artificial intelligence`.
- mark unavailable metric or period coverage as a caveat.

Disallowed revisions:

- invent missing data.
- query unapproved SQL tables.
- silently drop a planned company from comparison.
- exceed configured max retry budgets.

### 8. Answer Synthesis From Plan

Final answer synthesis should receive:

- original question
- research plan
- validation output
- structured SQL evidence
- document evidence
- warnings/caveats

The answer should explicitly satisfy the plan and avoid unplanned tangents.

Expected format:

- `Bottom Line`
- `Comparison Snapshot`
- `What Supports This`
- `Caveats`
- `Evidence Used`

The final formatting agent should continue converting raw citation labels into monotonic numbered citations with an evidence mapping table.

### 9. API And UI Trace

The API response should include the research plan and plan validation results.

Suggested response fields:

```json
{
  "research_plan": {},
  "plan_validation": {},
  "agent_trace": {}
}
```

The UI should show a compact version of the plan under `Analysis Plan`.

Recommended UI fields:

- companies
- research goal
- required metrics
- document themes
- planned sources
- validation warnings

Avoid showing long internal prompts or raw JSON by default. Put raw trace details behind an expander.

## Acceptance Criteria

### Functional

- The agent creates a structured research plan for every successful question.
- SQL/RAG/hybrid tool choices are derived from the plan.
- Comparative questions include explicit per-company evidence requirements.
- Missing evidence produces either a retry or a caveat.
- Final answers use numbered citations and an `Evidence Used` table.

### Behavioral

- For a Microsoft vs Alphabet AI/capex question, both companies must be represented in SQL evidence.
- If both companies require document evidence, retrieval should attempt both companies.
- If one company lacks document evidence, the answer must say so clearly.
- The answer should summarize, not dump raw rows.

### Testing

Add unit tests for:

- plan generation fallback.
- route/tier derivation from plan.
- SQL evidence coverage validation.
- RAG evidence coverage validation.
- retry decision when a planned company is missing document evidence.
- final API trace contains `research_plan`.

Add one integration-style test fixture for:

```text
Compare Microsoft and Alphabet on AI narrative and capex intensity over the last four quarters.
```

Expected:

- companies: `MSFT`, `GOOGL`
- required metrics: `capex_pct_revenue`, `rd_pct_revenue`, `revenue_growth_yoy`
- required sources: `structured`, `unstructured`
- tier: `deep_research`
- route: `hybrid`
- validation warns if Alphabet capex quarters are incomplete

## Implementation Notes

Suggested new modules:

- `agent/research_plan.py`: dataclasses or Pydantic models for plan and validation.
- `agent/research_planner.py`: LLM planner plus deterministic fallback.
- `agent/plan_executor.py`: execution orchestration from plan to tools.
- `agent/plan_validator.py`: evidence checks against plan requirements.

Suggested refactors:

- Keep `ResearchAgent` as the high-level orchestrator.
- Move current tier decision into a helper used by fallback planning.
- Pass plan context into `run_sql` and `retrieve_evidence`.
- Include `research_plan` in `AgentState.to_trace_dict()`.

## Risks And Mitigations

- Risk: LLM planner returns invalid plans.
  Mitigation: validate with Pydantic and fall back to deterministic planner.

- Risk: Plan becomes too verbose for simple questions.
  Mitigation: simple questions should produce minimal one- or two-step plans.

- Risk: More LLM calls increase latency.
  Mitigation: use deterministic fallback for obvious questions and reserve LLM planning/review for complex or comparative questions.

- Risk: Evidence retries become expensive.
  Mitigation: preserve fixed budgets by tier and expose retry counts in trace.

## Definition Of Done

This feature is done when:

- every answer has a structured research plan in trace;
- route, tier, and tool execution are plan-driven;
- validation compares evidence against the plan;
- weak evidence can trigger bounded retries or explicit caveats;
- the UI shows the plan in a readable way;
- tests cover plan generation, plan execution, validation, retry, and trace output.
