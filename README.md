# Public Company Research Assistant

[![CI](https://github.com/atulk1000/public-company-research-assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/atulk1000/public-company-research-assistant/actions/workflows/ci.yml)

A hybrid SQL + RAG research assistant for US public companies. It ingests structured SEC/XBRL metrics and unstructured SEC filing text, routes questions across SQL, retrieval, or both, and uses an LLM to produce grounded answers with citations and limitations.

This is intentionally built as a real data system rather than a thin chatbot wrapper:

- raw SEC files are persisted locally
- structured facts are normalized into Postgres
- filing text is chunked and embedded into `pgvector`
- new companies fetched in live mode are cached for future reuse
- freshness is tracked per company so the app can decide whether to reuse or refresh local data

Current source policy:

- official SEC filed data only
- no third-party finance sites, blogs, or unofficial transcript aggregators in the current version

## What It Demonstrates

- structured data ingestion from SEC submissions and company facts
- relational modeling in Postgres
- unstructured filing ingestion, cleaning, and chunking
- real embeddings stored in `pgvector`
- hybrid retrieval across lexical and vector signals
- LLM-based routing, SQL generation, and final answer synthesis
- evidence-backed answers over both numeric and text sources
- on-demand company resolution, ingestion, and local caching
- per-company freshness tracking for structured data, documents, and embeddings

## Code Quality

The repo includes explicit Python style/lint configuration in [pyproject.toml](./pyproject.toml) so the codebase is easy to review and maintain.

Current standards:

- `black` formatting
- `ruff` linting
- `isort` import ordering via Ruff

Typical cleanup commands:

```powershell
python -m black .
python -m ruff check . --fix
```

## Why This Is Interesting

Most public-company LLM demos stop at one of these layers:

- a chatbot over PDFs
- a metrics dashboard with no document reasoning
- a prompt wrapper over external finance APIs

This repo deliberately combines the hard parts of a grounded research product:

- structured financial modeling
- unstructured filing retrieval
- agentic LLM orchestration that plans the research task, validates evidence, and decides when to use SQL, retrieval, or both

The result is a system that can answer questions like:

- "Which company had the highest operating margin in the latest quarter?"
- "What did Apple say about AI in its latest filings?"
- "Compare Microsoft and Alphabet on AI narrative and capex intensity over the last four quarters."

## Current Scope

Default local demo universe starts with the Magnificent 7:

- `AAPL`
- `AMZN`
- `GOOGL`
- `META`
- `MSFT`
- `NVDA`
- `TSLA`

Live mode can additionally resolve and ingest other US public companies on demand, then persist them locally for future cache hits. The local research library is intentionally expandable: it starts with the Magnificent 7 seed set, then grows as live analysis fetches more companies. By default, batch ingestion jobs process every company already present in the local store; `TARGET_TICKERS` is only an optional filter when you want to refresh a smaller set.

Current structured sources:

- SEC submissions metadata
- SEC company facts / XBRL data
- fact-backed annual and quarterly forms such as `10-K`, `10-Q`, `20-F`, and `40-F` plus amendments

Current unstructured sources:

- recent `10-K`, `10-Q`, `8-K`, `20-F`, `6-K`, `40-F`, `DEF 14A`, `DEFM14A`, `PREM14A`, `S-1` / `S-3` / `S-4`, `424B`, `425`, `FWP`, Forms `3` / `4` / `5`, Schedule `13D` / `13G`, `13F-HR`, and tender / merger forms such as `SC TO` and `SC 14D9`
- high-value `8-K` / `6-K` `EX-99.*` exhibits, including SEC-filed earnings releases, guidance exhibits, and investor presentations when present in the filing package

Raw source files are persisted on disk under [data/raw/sec](./data/raw/sec), then loaded into Postgres for analysis and retrieval. Those raw SEC files stay local by default because [data/raw](./data/raw) is gitignored.

## App Modes

The Streamlit app has two user-facing modes:

- `Use live analysis` off: answer only from companies that are already loaded in the local Postgres + `pgvector` store
- `Use live analysis` on: resolve the company from the question, intelligently select and fetch the most relevant official SEC sources for that company, then run SQL, retrieval, or hybrid analysis

The current app prompt is:

- `Ask a question about any US public company finances`

In live mode, the app may:

1. extract the likely company / ticker from the question
2. validate it against the SEC company reference list
3. check whether the company is already cached locally and still fresh
4. ingest or refresh that company locally if needed
5. run SQL, RAG, or hybrid analysis
6. return a grounded answer with evidence and limitations

The live path supports both single-company and multi-company questions. Cold starts are slower, but every fetched company stays in the local store for future reuse.

## Product Screenshots

SQL-only question answered from structured SEC/XBRL-derived metrics:

![SQL-only query result](docs/screenshots/sql_only.png)

RAG question answered from embedded SEC filing text with document citations:

![RAG answer with SEC citations](docs/screenshots/rag_citations.png)

Hybrid question combining financial metrics with filing commentary:

![Hybrid SQL and RAG answer](docs/screenshots/hybrid_analysis.png)

Regenerate the screenshots from a running Streamlit app:

```powershell
$env:STREAMLIT_URL="http://localhost:8501"
node scripts\capture_demo_screenshots.mjs
```

## Demo Image

For an easier demo setup, the repo also includes a single-container demo image path:

- embedded Postgres + `pgvector`
- FastAPI API
- Streamlit UI
- bootstrap from checked-in raw SEC files under [data/raw/sec](./data/raw/sec)

Build it:

```powershell
docker build -f Dockerfile.demo -t public-company-research-assistant-demo .
```

Run it:

```powershell
docker run --rm `
  -p 5432:5432 `
  -p 8000:8000 `
  -p 8501:8501 `
  -v public-company-research-assistant-demo-data:/var/lib/postgresql/data `
  -e OPENAI_API_KEY=your_key_here `
  -e SEC_USER_AGENT="Public Company Research Assistant your-email@example.com" `
  public-company-research-assistant-demo
```

What this demo image does on first startup:

1. starts Postgres locally inside the container
2. applies the schema, seed data, and views
3. bootstraps the database from the repo's raw SEC files
4. generates embeddings if `OPENAI_API_KEY` is present
5. starts the API and Streamlit UI

Notes:

- first startup is slower because it bootstraps the demo dataset
- later restarts are faster if you reuse the mounted Docker volume shown above
- `OPENAI_API_KEY` is required for the full LLM + embedding experience; without it, the container can still bootstrap the local SEC data store but semantic retrieval and LLM synthesis will be limited
- this path is for demos only; the standard multi-container/manual flow remains the recommended development setup

## Architecture

```text
SEC APIs / filing documents
        |
        v
raw JSON + HTML on disk (data/raw/sec)
        |
        v
structured loaders + filing text parser
        |
        v
Postgres + pgvector
  - companies
  - filings
  - facts
  - derived_metrics
  - documents
  - document_chunks
  - company_data_freshness
        |
        v
LLM router -> SQL tool / retrieval tool / hybrid orchestration
        |
        v
LLM answer synthesis with citations and limitations
```

Key modules:

- [ingestion](./ingestion): SEC fetchers, raw-file persistence, filing parsing, chunking, embeddings
- [db](./db): schema, views, seed data
- [agent](./agent): company catalog, routing, SQL generation, retrieval, answer composition
- [retrieval](./retrieval): lexical search and reranking helpers
- [app](./app): FastAPI API and Streamlit demo UI
- [mcp_server](./mcp_server): optional MCP interface exposing governed research tools to MCP-compatible clients
- [evals](./evals): benchmark cases and evaluator for routing, retrieval, citations, and live freshness behavior

Important storage tables:

- `filings`: SEC filing metadata per company
- `facts`: normalized XBRL-style facts
- `derived_metrics`: modeled period-level metrics used by the SQL layer
- `documents`: parsed filing-level text documents
- `document_chunks`: chunk-level retrieval units plus embeddings
- `company_data_freshness`: last refresh timestamps for structured data, documents, and embeddings

## Current End-to-End Flow

1. Load filings and company facts from the SEC for the active company set.
2. Save raw JSON and filing HTML to disk.
3. Normalize facts and compute derived metrics in Postgres.
4. Parse filing text, chunk it, and store chunk embeddings in `pgvector`.
5. Ask a question through the API or Streamlit UI.
6. Let the LLM decide whether the question is `sql`, `rag`, or `hybrid`.
7. Generate SQL when needed, retrieve filing passages when needed, then synthesize the final answer with the LLM.

## Agentic Research Workflow

The current workflow has evolved from SQL/RAG/hybrid routing into a bounded agentic research workflow. The agent first creates a structured research plan with companies, metrics, document themes, evidence requirements, and validation checks. It then chooses the evidence route (`sql`, `rag`, or `hybrid`) and an execution tier before running the tools:

- SQL-fast for simple metric questions
- RAG-fast for simple filing or commentary questions
- Hybrid-fast for mixed single-company metric-plus-narrative questions
- Deep research for multi-company, comparative, ambiguous, or driver-analysis questions

Deep research supports multi-company comparative questions by running company-scoped retrieval, combining SQL and filing evidence where needed, validating coverage before final synthesis, and retrying weak document retrieval with expanded terms within a small fixed budget. The agent maintains an explicit trace/state, including the tier, route, companies, tools used, retries, validation warnings, SQL results, and retrieved document evidence.

Execution is budgeted and bounded. The agent does not invent financial numbers or rely on general model knowledge; final answers remain grounded in SQL results and SEC filing evidence, with missing evidence called out in the limitations.

Example trace for:

```text
Compare Nvidia and Microsoft AI revenue drivers over the last two years.
```

```json
{
  "question": "Compare Nvidia and Microsoft AI revenue drivers over the last two years.",
  "tier": "deep_research",
  "route": "hybrid",
  "companies": ["NVDA", "MSFT"],
  "tools_used": ["sql", "rag"],
  "retries": 0,
  "validation": {
    "passed": true,
    "missing_sql_companies": [],
    "missing_rag_companies": [],
    "warnings": [],
    "needs_retry": false
  }
}
```

## Live Analysis Flow

When `Use live analysis` is enabled, the request path is:

1. planner extracts the likely company, ticker, route, and source needs
2. resolver validates the company against the cached SEC company list
3. the app checks `company_data_freshness` to see whether local structured data, documents, and embeddings are still fresh
4. if needed, it fetches official SEC data for that company and loads it into Postgres / `pgvector`
5. SQL, retrieval, or hybrid analysis runs against the refreshed local store
6. the LLM writes the final answer from the retrieved evidence

This lets the app stay lightweight locally while still supporting on-demand analysis for companies that are not part of the default seed set.

Default freshness behavior:

- SEC company reference cache: 24 hours
- live company data cache: 24 hours
- if cached company data is still fresh, live mode reuses it rather than re-ingesting the company

## MCP Interface

The repo includes an optional Model Context Protocol server that exposes the research layer as governed tools for MCP-compatible agents and clients. The MCP server reuses the same Postgres, `pgvector`, SEC ingestion, retrieval, and answer-synthesis code as the Streamlit/API app.

Exposed MCP tools:

- `query_financial_metrics`: read-only structured metrics from `v_company_period_metrics`
- `retrieve_filing_context`: company-scoped SEC filing retrieval for a topic
- `refresh_company_data`: explicit one-company SEC refresh through the live ingestion path
- `compare_company_metrics`: read-only multi-company metric comparison, capped at five tickers
- `answer_financial_question`: run the existing scoped research agent and return the grounded answer plus trace

Exposed MCP resources:

- `companies://loaded`: companies currently present in the local research store
- `metrics://schema`: available metric fields and descriptions
- `sources://sec-policy`: current SEC-only source policy
- `freshness://companies`: per-company refresh timestamps
- `agent://capabilities`: exposed tools, limits, and guardrails

The MCP layer is intentionally constrained:

- no arbitrary SQL execution
- validated tickers and metric allowlists
- read tools capped by row/chunk limits
- live refresh is explicit and limited to one company per call
- final answers still pass through the app's public-company financial scope guard

Run the MCP server locally:

```powershell
python -m mcp_server.server
```

Run it through Docker Compose as an opt-in profile:

```powershell
docker compose --profile mcp run --rm mcp
```

## Source Policy

The current app intentionally uses only official SEC-hosted company filings and SEC API data. This keeps the evidence set low-noise and reproducible while the core hybrid reasoning workflow is being built out.

Used now:

- SEC submissions metadata
- SEC XBRL / company facts
- SEC-hosted filing documents
- SEC ownership, proxy, registration/prospectus, tender, merger, and institutional-holdings primary filing documents
- earnings releases and investor decks when they are filed as `EX-99`, `EX-99.1`, `EX-99.01`, `EX-99.2`, or `EX-99.02` exhibits inside `8-K` / `6-K` filing packages

Not used yet:

- lower-priority exhibit documents such as contracts, certifications, graphics, and PDFs outside the high-value `EX-99.*` family
- third-party market-data websites
- unofficial earnings-call transcript sites
- finance blogs or media summaries
- non-SEC investor-relations sources such as decks or press-release pages that are not filed with the SEC

This is a deliberate product choice: the current version optimizes for reproducible, low-noise evidence rather than broad web coverage.

## Local Setup

The repo supports two ways to run it:

- **Demo path**: one container using [Dockerfile.demo](./Dockerfile.demo)
- **Manual/dev path**: Postgres + API + Streamlit via [docker-compose.yml](./docker-compose.yml)

### 1. Create a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Create your local env file

```powershell
Copy-Item .env.example .env
```

Set these values in [`.env`](./.env):

```env
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-5-mini
OPENAI_REASONING_EFFORT=low
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/company_assistant
EMBEDDING_MODEL=text-embedding-3-small
SEC_USER_AGENT=Public Company Research Assistant your-email@example.com
```

Important:

- if you run the app in Docker, use `postgres` as the database host
- if you run Python directly on your machine, use `localhost`
- do not commit your real `.env`

### 3. Start the local stack

```powershell
docker compose up -d
```

Services:

- API: [http://localhost:8000](http://localhost:8000)
- Streamlit UI: [http://localhost:8501](http://localhost:8501)
- Postgres: `localhost:5432`

## Ingestion Workflow

Apply the schema and views if needed:

```powershell
docker compose exec postgres psql -U postgres -d company_assistant -f /app/db/schema.sql
docker compose exec postgres psql -U postgres -d company_assistant -f /app/db/seed.sql
docker compose exec postgres psql -U postgres -d company_assistant -f /app/db/views.sql
```

Load structured SEC data:

```powershell
docker compose run --rm api python ingestion/load_sec_data.py
```

By default this refreshes all companies in the local `companies` table, including companies previously fetched by live analysis. To limit a run, set `TARGET_TICKERS`, for example `TARGET_TICKERS=MSFT,NVDA`.

Load filing text and chunk it:

```powershell
docker compose run --rm api python ingestion/load_filing_texts.py
```

Generate embeddings for all chunks:

```powershell
docker compose run --rm api python ingestion/embed_chunks.py
```

The current pipeline writes:

- raw SEC JSON and filing HTML to [data/raw/sec](./data/raw/sec)
- structured metrics to Postgres, including non-USD annual / quarterly fact sets where available
- filing chunks to `document_chunks`
- embeddings to `document_chunks.embedding`
- refresh timestamps to `company_data_freshness`

## Persistence And Reuse

When live mode fetches a new company:

- the company is inserted into `companies`
- structured data is written to `filings`, `facts`, and `derived_metrics`
- filing text is written to `documents` and `document_chunks`
- embeddings are stored in `document_chunks.embedding`
- refresh times are stored in `company_data_freshness`

That means a company fetched once in live mode becomes part of the local research store and can be reused on later questions without a full refetch if the cache is still fresh.

## Evaluation

The repo includes a benchmark-driven evaluation layer rather than route-only spot checks.

Artifacts:

- benchmark cases: [evals/benchmark_questions.yaml](./evals/benchmark_questions.yaml)
- evaluator: [evals/run_eval.py](./evals/run_eval.py)
- evaluation notes: [docs/evaluation.md](./docs/evaluation.md)
- latest sample results: [docs/eval_results.md](./docs/eval_results.md)

The benchmark covers:

- 25 benchmark cases today
- cached and live analysis modes
- SQL-only, RAG-only, and hybrid questions
- single-company and multi-company prompts
- positive cases and graceful-failure cases
- preloaded companies plus live-ingested companies such as `AAPL`

Tracked metrics:

- routing accuracy
- status accuracy
- company resolution accuracy
- SQL generation rate
- SQL execution validity
- retrieval hit rate
- citation coverage
- faithfulness proxy
- freshness metadata rate for live mode

Run the evaluator:

```powershell
python evals\run_eval.py
```

The runner writes a machine-readable report to:

- `evals/latest_eval_report.json`

This is still a pragmatic benchmark layer rather than a full research-grade evaluator, but it is designed to measure the product behaviors that matter for a hybrid SQL + RAG assistant.

Latest sample run:

- 25 benchmark cases
- 96.00% pass rate
- 95.83% routing accuracy
- 100.00% retrieval hit rate
- 100.00% citation coverage
- 100.00% freshness metadata rate

## How To Test

### UI

Open [http://localhost:8501](http://localhost:8501) and try:

- turn `Use live analysis` on for on-demand company resolution + ingestion
- turn it off to answer only from the already loaded local dataset
- `Which company had the highest operating margin in the latest reported quarter?`
- `How has capex intensity changed for Microsoft over the last four quarters?`
- `What themes dominate Alphabet management commentary around AI?`
- `Compare Microsoft and Alphabet on AI narrative and capex intensity over the last four quarters.`
- `What did Apple say about AI in its latest filings?`

### API

```powershell
Invoke-RestMethod -Method Post `
  -Uri "http://localhost:8000/ask" `
  -ContentType "application/json" `
  -Body '{"question":"Compare Microsoft and Alphabet on AI narrative and capex intensity over the last four quarters.","live_analysis":true}'
```

## Example Capabilities

- SQL-only reasoning over `v_company_period_metrics`
- vector + lexical retrieval over real filing text
- hybrid reasoning that combines numeric trends with management commentary
- company-aware retrieval when a question names multiple companies
- quarter-aware SQL validation for quarter-based questions
- broader SEC offline ingestion across domestic, foreign-issuer, event, proxy, and registration statement filings
- SEC-filed `EX-99.*` exhibit retrieval for earnings releases and investor presentations
- on-demand ingestion plus local cache reuse for newly requested companies

## Repo Walkthrough

If someone is inspecting the repo quickly, the highest-signal places to look are:

- [app/ui_streamlit.py](./app/ui_streamlit.py): user-facing flow, live toggle, source policy, evidence rendering
- [agent/hybrid_tool.py](./agent/hybrid_tool.py): top-level cached vs live orchestration
- [agent/sql_tool.py](./agent/sql_tool.py): LLM-assisted SQL generation with local execution
- [agent/rag_tool.py](./agent/rag_tool.py): retrieval over stored filing chunks
- [ingestion/live_ingest.py](./ingestion/live_ingest.py): on-demand company ingest and cache decisions
- [ingestion/freshness.py](./ingestion/freshness.py): per-company freshness tracking
- [db/schema.sql](./db/schema.sql): the normalized storage model
- [evals/run_eval.py](./evals/run_eval.py): measurable checks for routing, retrieval, citations, and freshness
- [docs/evaluation.md](./docs/evaluation.md): what the benchmark measures and what it still does not

## Current Limitations

- the default seed universe is intentionally small for local iteration, though live mode can expand the local library
- non-SEC sources such as transcripts, non-filed investor decks, and IR-hosted earnings releases are not ingested yet
- retrieval quality is strong enough for demos, but still improvable
- the Streamlit UI is an MVP, not a polished production frontend
- evaluation is now benchmark-driven, but citation coverage and faithfulness are still heuristic rather than claim-by-claim verified
- live mode supports multi-company questions, but it is not intended for bulk market-wide ingestion

## Why This Repo Is Useful

This project is meant to show more than prompt engineering. It demonstrates an end-to-end system for:

- modeling structured and unstructured data together
- deciding when SQL, retrieval, or hybrid reasoning is appropriate
- grounding LLM answers in actual source evidence
- building a reproducible local workflow with raw data, a database, and a queryable application

## Next Improvements

- add more public data sources such as earnings call transcripts, market data, analyst consensus, and non-SEC investor-relations materials
- improve section-aware parsing for filings
- deepen evaluation with claim-level faithfulness checks and retrieval relevance labels
- improve citation rendering and analyst-style presentation in the UI
