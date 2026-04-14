# Public Company Research Assistant

A hybrid SQL + RAG research assistant for public companies. It ingests structured SEC/XBRL metrics and unstructured SEC filing text, routes questions across SQL, retrieval, or both, and uses an LLM to produce grounded answers with citations and limitations.

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

## Current Scope

The current local dataset covers:

- `MSFT`
- `GOOGL`
- `AMZN`

Current structured sources:

- SEC submissions metadata
- SEC company facts / XBRL data
- fact-backed annual and quarterly forms such as `10-K`, `10-Q`, `20-F`, and `40-F` plus amendments

Current unstructured sources:

- recent `10-K`, `10-Q`, `8-K`, `20-F`, `6-K`, `40-F`, `DEF 14A`, and `S-1` / `S-3` / `S-4` filings

Raw source files are persisted on disk under [data/raw/sec](./data/raw/sec), then loaded into Postgres for analysis and retrieval.
Those raw SEC files stay local by default because [data/raw](./data/raw) is gitignored.

## App Modes

The Streamlit app has two user-facing modes:

- `Use live analysis` off: answer only from companies that are already loaded in the local Postgres + `pgvector` store
- `Use live analysis` on: resolve the company from the question, intelligently select and fetch the most relevant official SEC sources for that company, then run SQL, retrieval, or hybrid analysis

The current app prompt is:

- `Ask a question about any US public company finances`

In live mode, the app may:

1. extract the likely company / ticker from the question
2. validate it against the SEC company reference list
3. ingest or refresh that company locally
4. run SQL, RAG, or hybrid analysis
5. return a grounded answer with evidence and limitations

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
- [evals](./evals): benchmark scaffolding for offline evaluation

## Current End-to-End Flow

1. Load filings and company facts from the SEC for the active company set.
2. Save raw JSON and filing HTML to disk.
3. Normalize facts and compute derived metrics in Postgres.
4. Parse filing text, chunk it, and store chunk embeddings in `pgvector`.
5. Ask a question through the API or Streamlit UI.
6. Let the LLM decide whether the question is `sql`, `rag`, or `hybrid`.
7. Generate SQL when needed, retrieve filing passages when needed, then synthesize the final answer with the LLM.

## Live Analysis Flow

When `Use live analysis` is enabled, the request path is:

1. planner extracts the likely company, ticker, route, and source needs
2. resolver validates the company against the cached SEC company list
3. the app checks whether local data for that company is fresh enough
4. if needed, it fetches official SEC data for that company and loads it into Postgres / `pgvector`
5. SQL, retrieval, or hybrid analysis runs against the refreshed local store
6. the LLM writes the final answer from the retrieved evidence

This lets the app stay lightweight locally while still supporting on-demand analysis for companies that are not preloaded.

## Source Policy

The current app intentionally uses only official SEC-hosted company filings and SEC API data. This keeps the evidence set low-noise and reproducible while the core hybrid reasoning workflow is being built out.

Used now:

- SEC submissions metadata
- SEC XBRL / company facts
- SEC-hosted filing documents

Not used yet:

- third-party market-data websites
- unofficial earnings-call transcript sites
- finance blogs or media summaries
- non-SEC investor-relations sources such as decks or press-release pages

## Local Setup

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

## Current Limitations

- the company universe is still intentionally small for local iteration
- non-SEC sources such as transcripts, investor decks, and IR-hosted earnings releases are not ingested yet
- retrieval quality is strong enough for demos, but still improvable
- the Streamlit UI is an MVP, not a polished production frontend
- evaluation exists as scaffolding and should be expanded into a fuller benchmark report

## Why This Repo Is Useful

This project is meant to show more than prompt engineering. It demonstrates an end-to-end system for:

- modeling structured and unstructured data together
- deciding when SQL, retrieval, or hybrid reasoning is appropriate
- grounding LLM answers in actual source evidence
- building a reproducible local workflow with raw data, a database, and a queryable application

## Next Improvements

- add more public data sources such as `8-K` exhibits, proxy statements, earnings call transcripts, and investor presentations
- improve section-aware parsing for filings
- expand benchmark questions and retrieval-quality evaluation
- improve citation rendering and analyst-style presentation in the UI
