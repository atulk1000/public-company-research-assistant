from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import statistics
import sys
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.hybrid_tool import answer_question


CITATION_PATTERN = re.compile(r"\[(?:SQL|DOC):[^\]]+\]")


@dataclass
class EvalCase:
    id: str
    question: str
    expected_route: str
    expected_companies: list[str]
    expected_period: str
    live_analysis: bool
    requires_structured: bool
    requires_retrieval: bool
    require_nonempty_sql_rows: bool
    require_nonempty_retrieval: bool
    require_citations: bool
    gold_notes: str
    expected_status: str = "success"


@dataclass
class CaseResult:
    id: str
    question: str
    live_analysis: bool
    expected_status: str
    actual_status: str
    expected_route: str
    actual_route: str
    route_match: bool
    status_match: bool
    company_match: bool
    sql_present: bool
    sql_rows_nonempty: bool
    retrieval_present: bool
    retrieval_nonempty: bool
    citations_present: bool
    faithfulness_proxy_pass: bool
    freshness_present: bool
    passed: bool
    notes: list[str]


def load_benchmark_questions() -> list[EvalCase]:
    benchmark_path = Path(__file__).with_name("benchmark_questions.yaml")
    raw_cases = yaml.safe_load(benchmark_path.read_text(encoding="utf-8")) or []
    return [EvalCase(**case) for case in raw_cases]


def resolved_tickers(response: dict[str, Any]) -> set[str]:
    tickers: set[str] = set()

    resolved = response.get("resolved_company") or {}
    if resolved.get("ticker"):
        tickers.add(str(resolved["ticker"]).upper())

    planning = response.get("planning") or {}
    if planning.get("ticker"):
        tickers.add(str(planning["ticker"]).upper())

    structured_rows = (response.get("structured_evidence") or {}).get("rows") or []
    for row in structured_rows:
        ticker = row.get("ticker")
        if ticker:
            tickers.add(str(ticker).upper())

    retrieved_rows = response.get("retrieved_evidence") or []
    for item in retrieved_rows:
        metadata = item.get("metadata") or {}
        ticker = metadata.get("ticker")
        if ticker:
            tickers.add(str(ticker).upper())

    return tickers


def evaluate_case(case: EvalCase) -> CaseResult:
    response = answer_question(case.question, live_analysis=case.live_analysis)

    actual_status = response.get("status", "unknown")
    actual_route = response.get("route", "unknown")
    status_match = actual_status == case.expected_status
    route_match = actual_route == case.expected_route

    actual_tickers = resolved_tickers(response)
    expected_tickers = {ticker.upper() for ticker in case.expected_companies}
    company_match = expected_tickers.issubset(actual_tickers) if expected_tickers else True

    structured = response.get("structured_evidence") or {}
    retrieved = response.get("retrieved_evidence") or []
    answer = response.get("answer", "")

    sql_present = bool(structured.get("sql"))
    sql_rows_nonempty = bool(structured.get("rows"))
    retrieval_present = len(retrieved) > 0
    retrieval_nonempty = len(retrieved) > 0
    citations_present = bool(CITATION_PATTERN.search(answer))
    faithfulness_proxy_pass = True
    freshness_present = bool((response.get("live_ingestion") or {}).get("freshness"))

    notes: list[str] = []

    if not status_match:
        notes.append(f"expected status={case.expected_status}, got {actual_status}")
    if case.expected_status == "success" and not route_match:
        notes.append(f"expected route={case.expected_route}, got {actual_route}")
    if expected_tickers and not company_match:
        notes.append(f"expected companies {sorted(expected_tickers)}, got {sorted(actual_tickers)}")

    if case.requires_structured and not sql_present:
        notes.append("structured evidence missing")
        faithfulness_proxy_pass = False
    if case.require_nonempty_sql_rows and not sql_rows_nonempty:
        notes.append("structured query returned no rows")
        faithfulness_proxy_pass = False

    if case.requires_retrieval and not retrieval_present:
        notes.append("retrieved evidence missing")
        faithfulness_proxy_pass = False
    if case.require_nonempty_retrieval and not retrieval_nonempty:
        notes.append("retrieved evidence returned no chunks")
        faithfulness_proxy_pass = False

    if case.require_citations and not citations_present:
        notes.append("answer did not include citations")
        faithfulness_proxy_pass = False

    if case.live_analysis and case.expected_status == "success" and not freshness_present:
        notes.append("live analysis response did not expose freshness metadata")
        faithfulness_proxy_pass = False

    passed = status_match and (
        actual_status != "success"
        or (
            route_match
            and company_match
            and (not case.requires_structured or sql_present)
            and (not case.require_nonempty_sql_rows or sql_rows_nonempty)
            and (not case.requires_retrieval or retrieval_present)
            and (not case.require_nonempty_retrieval or retrieval_nonempty)
            and (not case.require_citations or citations_present)
            and (not case.live_analysis or freshness_present or case.expected_status != "success")
        )
    )

    return CaseResult(
        id=case.id,
        question=case.question,
        live_analysis=case.live_analysis,
        expected_status=case.expected_status,
        actual_status=actual_status,
        expected_route=case.expected_route,
        actual_route=actual_route,
        route_match=route_match,
        status_match=status_match,
        company_match=company_match,
        sql_present=sql_present,
        sql_rows_nonempty=sql_rows_nonempty,
        retrieval_present=retrieval_present,
        retrieval_nonempty=retrieval_nonempty,
        citations_present=citations_present,
        faithfulness_proxy_pass=faithfulness_proxy_pass,
        freshness_present=freshness_present,
        passed=passed,
        notes=notes,
    )


def ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def aggregate_metrics(cases: list[EvalCase], results: list[CaseResult]) -> dict[str, Any]:
    success_results = [result for case, result in zip(cases, results, strict=True) if case.expected_status == "success"]

    structured_results = [
        result for case, result in zip(cases, results, strict=True)
        if case.requires_structured and case.expected_status == "success"
    ]

    retrieval_results = [
        result for case, result in zip(cases, results, strict=True)
        if case.requires_retrieval and case.expected_status == "success"
    ]

    citation_results = [
        result for case, result in zip(cases, results, strict=True)
        if case.require_citations and case.expected_status == "success"
    ]

    live_results = [
        result for case, result in zip(cases, results, strict=True)
        if case.live_analysis and case.expected_status == "success"
    ]

    metrics = {
        "case_count": len(cases),
        "successful_case_count": len(success_results),
        "pass_rate": ratio(sum(result.passed for result in results), len(results)),
        "routing_accuracy": ratio(sum(result.route_match for result in success_results), len(success_results)),
        "status_accuracy": ratio(sum(result.status_match for result in results), len(results)),
        "company_resolution_accuracy": ratio(
            sum(result.company_match for result in success_results),
            len(success_results),
        ),
        "sql_generation_rate": ratio(sum(result.sql_present for result in structured_results), len(structured_results)),
        "sql_execution_validity": ratio(
            sum(result.sql_rows_nonempty for result in structured_results),
            len(structured_results),
        ),
        "retrieval_hit_rate": ratio(
            sum(result.retrieval_nonempty for result in retrieval_results),
            len(retrieval_results),
        ),
        "citation_coverage": ratio(sum(result.citations_present for result in citation_results), len(citation_results)),
        "faithfulness_proxy": ratio(
            sum(result.faithfulness_proxy_pass for result in success_results),
            len(success_results),
        ),
        "freshness_metadata_rate": ratio(sum(result.freshness_present for result in live_results), len(live_results)),
        "notes_per_case_avg": statistics.mean(len(result.notes) for result in results) if results else 0.0,
    }
    return metrics


def print_summary(cases: list[EvalCase], results: list[CaseResult], metrics: dict[str, Any]) -> None:
    print("Public Company Research Assistant evaluation summary")
    print(f"- benchmark cases: {metrics['case_count']}")
    print(f"- pass rate: {metrics['pass_rate']:.2%}")
    print(f"- routing accuracy: {metrics['routing_accuracy']:.2%}")
    print(f"- status accuracy: {metrics['status_accuracy']:.2%}")
    print(f"- company resolution accuracy: {metrics['company_resolution_accuracy']:.2%}")
    print(f"- SQL execution validity: {metrics['sql_execution_validity']:.2%}")
    print(f"- retrieval hit rate: {metrics['retrieval_hit_rate']:.2%}")
    print(f"- citation coverage: {metrics['citation_coverage']:.2%}")
    print(f"- faithfulness proxy: {metrics['faithfulness_proxy']:.2%}")
    print(f"- freshness metadata rate: {metrics['freshness_metadata_rate']:.2%}")
    print("")

    for case, result in zip(cases, results, strict=True):
        status_marker = "PASS" if result.passed else "FAIL"
        mode = "live" if case.live_analysis else "cached"
        print(
            f"[{status_marker}] {case.id} | mode={mode} | expected={case.expected_route}/{case.expected_status} "
            f"| actual={result.actual_route}/{result.actual_status}"
        )
        if result.notes:
            for note in result.notes:
                print(f"  - {note}")


def write_json_report(cases: list[EvalCase], results: list[CaseResult], metrics: dict[str, Any]) -> Path:
    report_path = Path(__file__).with_name("latest_eval_report.json")
    payload = {
        "metrics": metrics,
        "cases": [asdict(case) for case in cases],
        "results": [asdict(result) for result in results],
    }
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return report_path


def main() -> None:
    cases = load_benchmark_questions()
    results = [evaluate_case(case) for case in cases]
    metrics = aggregate_metrics(cases, results)
    print_summary(cases, results, metrics)
    report_path = write_json_report(cases, results, metrics)
    print("")
    print(f"Wrote JSON report to {report_path}")


if __name__ == "__main__":
    main()
