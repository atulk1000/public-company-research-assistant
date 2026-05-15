# Latest Evaluation Results

Sample run date: 2026-05-15

Environment:

- Docker Compose API container
- Postgres + `pgvector`
- official SEC-only local corpus
- OpenAI-backed routing, SQL generation, retrieval embeddings, and answer synthesis

Command:

```powershell
docker compose exec api python evals/run_eval.py
```

## Summary Metrics

| Metric | Result |
| --- | ---: |
| Benchmark cases | 25 |
| Pass rate | 96.00% |
| Routing accuracy | 95.83% |
| Status accuracy | 100.00% |
| Company resolution accuracy | 100.00% |
| SQL generation rate | 100.00% |
| SQL execution validity | 93.75% |
| Retrieval hit rate | 100.00% |
| Citation coverage | 100.00% |
| Faithfulness proxy | 100.00% |
| Freshness metadata rate | 100.00% |

## What Passed

The benchmark passed the main product behaviors the repo is meant to demonstrate:

- SQL-only financial metric questions over `v_company_period_metrics`
- RAG-only questions over SEC filing chunks
- hybrid questions combining metrics and filing commentary
- live-mode company ingestion and cache freshness metadata
- graceful failure for an invalid ticker
- citation coverage across successful cases requiring citations

## Remaining Failure

One benchmark case failed in this run:

| Case | Expected | Actual | Issue |
| --- | --- | --- | --- |
| `route_rag_amzn_strategy` | `rag` | `hybrid` | The model chose to include structured context for a broad strategy question. The answer still had evidence, citations, and company scope; the failure is a route-label disagreement. |

## Interpretation

This run is useful because it shows both strengths and the next engineering targets.

The strong signals are:

- the system can execute SQL-backed, RAG-backed, and hybrid workflows end to end
- citations are now consistently present in successful cited-answer cases
- live-mode freshness metadata is exposed consistently
- retrieval returns evidence for every retrieval case

The main improvement area is stricter route calibration:

- broad strategy questions sometimes get classified as `hybrid` when the benchmark expects `rag`
- future eval work should separate acceptable alternate routes from strict route mismatches

That is a product-quality issue rather than a missing architecture issue.
