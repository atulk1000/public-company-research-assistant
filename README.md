# Public Company Research Assistant

A hybrid SQL + RAG analyst that answers questions about public companies using structured SEC/XBRL data and unstructured filings, letters, and management commentary, with grounded citations.

## Why This Project

Financial research questions rarely live in one modality. Some require precise structured metrics, others require qualitative evidence from filings, and many require both. This project routes questions across SQL and retrieval, then composes grounded answers with citations.

This repo is designed to showcase:

- relational data modeling for company and filing data
- ingestion and chunking of unstructured documents
- hybrid retrieval over lexical and semantic signals
- query routing across SQL, retrieval, and hybrid reasoning
- evaluation of answer quality, grounding, and routing behavior

## v1 Scope

The first iteration is intentionally narrow so it feels like a real analyst tool instead of a generic chatbot.

- Companies: Microsoft, Alphabet, Amazon
- Metrics: revenue growth, gross margin, operating margin, capex as % revenue, R&D as % revenue
- Documents: 10-K / 10-Q plus curated shareholder letters or management commentary
- UI: FastAPI backend plus a lightweight Streamlit interface
- Eval set: 15 benchmark questions covering SQL-only, retrieval-only, and hybrid workflows

## Narrative vs Numbers Angle

The core job of the system is to answer:

`Do management claims match the reported numbers?`

That framing creates a clean, explainable story:

- SQL answers metric-heavy questions
- retrieval answers commentary-heavy questions
- hybrid reasoning handles questions that need both

## Architecture

1. `ingestion/` pulls structured SEC data and normalizes documents.
2. `db/` stores relational tables, derived metrics, and vector-enabled chunks.
3. `retrieval/` runs lexical, vector, and hybrid search.
4. `agent/` routes each question and orchestrates SQL / RAG tools.
5. `app/` exposes an API and a simple UI.
6. `evals/` runs benchmark questions and captures results.

See [docs/architecture.md](docs/architecture.md) and [docs/build_plan.md](docs/build_plan.md) for the concrete implementation plan.

## Local Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Start the API:

```bash
uvicorn app.api:app --reload
```

Start the Streamlit UI:

```bash
streamlit run app/ui_streamlit.py
```

Run the starter evaluation:

```bash
python evals/run_eval.py
```

## Demo Questions

- Which company had the highest operating margin in the latest reported quarter?
- How has capex intensity changed for Microsoft over the last four quarters?
- What themes dominate Alphabet's latest management commentary around AI?
- Compare Microsoft and Amazon on cloud-related narrative and revenue trend.
- Which company had improving margins but cautious management tone?

## Evaluation Goals

The repo should report:

- routing accuracy
- citation coverage
- groundedness
- answer correctness

## Next Build Steps

- finish SEC ingestion for 3 target companies
- create derived metric views in Postgres
- add document chunking and embeddings
- wire live OpenAI responses with citations
- add reranking and answer-level evaluation
