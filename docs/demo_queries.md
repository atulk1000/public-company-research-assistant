# Demo Queries

Use these questions to demo the repo in a way that highlights the three main paths: SQL-only, RAG-only, and hybrid analysis.

## High-Signal Demos

### 1. SQL-only

Question:

- `Which company had the highest operating margin in the latest reported quarter?`

What this shows:

- structured metrics in Postgres
- LLM route selection to `sql`
- generated SQL over `v_company_period_metrics`
- grounded answer with numeric evidence

Suggested screenshot:

- final answer + structured evidence table + generated SQL

### 2. RAG-only

Question:

- `What themes dominate Alphabet's latest management commentary around AI?`

What this shows:

- retrieval over filing chunks in `pgvector`
- citation-backed narrative synthesis
- official SEC-source grounding rather than generic web search

Suggested screenshot:

- final answer + retrieved evidence panel with citations and source metadata

### 3. Hybrid

Question:

- `Compare Microsoft and Alphabet on AI narrative and capex intensity over the last four quarters.`

What this shows:

- hybrid route selection
- numeric SQL evidence plus filing passages
- final synthesis that distinguishes fact from inference

Suggested screenshot:

- answer + structured evidence + retrieved evidence in the same view

## Additional Good Questions

- `How has capex intensity changed for Microsoft over the last four quarters?`
- `Summarize Amazon's capex commentary with numeric context.`
- `Show an example where narrative sounded strong but financial evidence was mixed.`
- `What did Apple say about AI in its latest filings?`
