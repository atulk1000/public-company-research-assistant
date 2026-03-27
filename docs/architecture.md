# Architecture

## Goal

Build a portfolio-quality analyst system that can answer public-company questions across structured and unstructured data, then produce grounded conclusions with citations.

## Core Flow

1. Ingestion
   - fetch company metadata
   - fetch filing metadata
   - fetch company facts
   - parse and chunk unstructured documents
   - embed document chunks

2. Storage
   - Postgres stores companies, filings, facts, and derived metrics
   - `pgvector` stores embeddings alongside chunk metadata

3. Retrieval and Tools
   - SQL tool handles metric-heavy questions
   - lexical search handles exact phrase matches
   - vector search handles semantic matches
   - hybrid search combines both

4. Orchestration
   - router decides `sql`, `rag`, or `hybrid`
   - answer composer merges structured evidence and retrieved passages
   - final answer should separate facts from inference

5. Evaluation
   - run benchmark questions
   - measure routing accuracy first
   - add groundedness, citations, and correctness next

## v1 Tradeoffs

- start with 3 companies, not 50
- keep a rules-based router first
- use deterministic placeholder data until live ingestion is stable
- prefer a simple UI over polishing frontend too early
