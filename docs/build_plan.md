# 1-Week Build Plan

## Day 1: Repo and Schema

- finalize project scope and target companies
- stand up Postgres with `pgvector`
- create base schema in `db/schema.sql`
- seed target companies in `db/seed.sql`
- write README framing and demo questions

Deliverable:
The repo runs locally, the database starts, and the project story is clear.

## Day 2: Structured Data Ingestion

- implement SEC company and filings fetchers
- fetch company facts for the target companies
- normalize a first pass of facts into relational tables
- document the core concepts you will keep for v1

Deliverable:
A repeatable ingestion script that pulls official SEC JSON and stores a minimal set of facts.

## Day 3: Derived Metrics Layer

- compute revenue growth, gross margin, operating margin, capex % revenue, and R&D % revenue
- create or refine `db/views.sql`
- validate the metrics in a notebook or quick script
- capture one screenshot or table for the README

Deliverable:
Usable period-by-period metric outputs for Microsoft, Alphabet, and Amazon.

## Day 4: Document Parsing and Retrieval

- collect 10-K / 10-Q text and one extra commentary source per company
- parse raw text and chunk documents with metadata
- wire lexical search and placeholder vector search
- test retrieval with commentary-heavy questions

Deliverable:
Top passages can be retrieved for prompts like "What did management say about AI demand?"

## Day 5: Query Routing and Hybrid Answers

- refine routing logic in `agent/router.py`
- connect SQL outputs and retrieval outputs in the answer pipeline
- add citations and source metadata in the response shape
- test 10 end-to-end demo questions manually

Deliverable:
A working `sql` / `rag` / `hybrid` path with grounded evidence in the output.

## Day 6: Evaluation

- expand `evals/benchmark_questions.yaml` to 15 questions
- score routing accuracy
- add starter groundedness and citation checks
- log failures and write short notes on why each failed

Deliverable:
An evaluation script and a small failure analysis loop.

## Day 7: Portfolio Polish

- tighten README copy and visuals
- add architecture and schema diagrams
- save 2 to 3 screenshots or sample outputs
- clean naming, comments, and setup docs
- prepare the initial GitHub upload

Deliverable:
A portfolio-ready v1 repo that tells a clear story in under 2 minutes of skim time.

## Stretch Goals

- replace fake embeddings with live embeddings
- add reranking
- support earnings-call transcripts
- store evaluation runs in Postgres
- add notebook-based error analysis
