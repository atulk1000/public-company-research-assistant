# Evaluation Approach

This repo does not treat evaluation as a single route-classification check. The goal is to measure whether the assistant behaves like a grounded product system across routing, SQL generation, retrieval, citations, and live freshness behavior.

## Benchmark Design

The benchmark set lives in [evals/benchmark_questions.yaml](../evals/benchmark_questions.yaml). It now covers:

- cached analysis and live analysis
- SQL-only, RAG-only, and hybrid questions
- single-company and multi-company prompts
- structured numeric questions, narrative filing questions, and cross-source questions
- positive and negative cases such as invalid tickers or partially supported source coverage

Current benchmark companies include:

- `MSFT`
- `GOOGL`
- `AMZN`
- `AAPL`
- `NBIS`

The benchmark schema supports:

- expected route
- expected company/ticker coverage
- expected status (`success` vs `not_found`)
- whether structured evidence is required
- whether retrieved filing evidence is required
- whether non-empty SQL rows are required
- whether non-empty retrieval output is required
- whether the final answer should include citations

## Metrics Tracked

The evaluator in [evals/run_eval.py](../evals/run_eval.py) reports:

- **Pass rate**: overall benchmark pass rate
- **Routing accuracy**: expected route vs actual route on successful cases
- **Status accuracy**: expected status vs actual status, including graceful failures
- **Company resolution accuracy**: whether expected company tickers are preserved or resolved
- **SQL generation rate**: whether structured cases actually produce SQL evidence
- **SQL execution validity**: whether structured cases return non-empty SQL results when expected
- **Retrieval hit rate**: whether retrieval cases return filing chunks when expected
- **Citation coverage**: whether answers include citations on cases that require them
- **Faithfulness proxy**: heuristic check that required evidence types and citations are present
- **Freshness metadata rate**: whether live-mode answers surface freshness metadata for cached/refreshed companies

These are intentionally pragmatic metrics: they are not a substitute for human review, but they are much more informative than route-only accuracy.

## How To Run

From the repo root:

```powershell
python evals\run_eval.py
```

The runner prints an aggregate summary and writes a machine-readable report to:

- [evals/latest_eval_report.json](../evals/latest_eval_report.json)

## Current Limitations

The evaluation layer is still heuristic in a few places:

- citation coverage is measured by presence of citation markers, not semantic claim-by-claim attribution
- faithfulness is a proxy based on evidence availability and citation presence, not a full statement verifier
- live benchmarks depend on local environment, model availability, and source freshness

Even with those limits, this evaluation layer is intended to show product thinking:

- define expected system behavior explicitly
- test more than one failure mode
- make routing, retrieval, and grounding measurable
