from __future__ import annotations

from agent.research_plan import ResearchPlan


def validate_plan_evidence(
    plan: ResearchPlan,
    sql_results: dict | None,
    rag_results: list[dict] | None,
) -> dict:
    sql_rows = sql_results.get("rows") if isinstance(sql_results, dict) else []
    sql_rows = sql_rows or []
    rag_results = rag_results or []

    sql_companies = {row.get("ticker") for row in sql_rows if row.get("ticker")}
    rag_companies = {
        item.get("metadata", {}).get("ticker")
        for item in rag_results
        if item.get("metadata", {}).get("ticker")
    }

    missing_sql_companies = [
        ticker for ticker in plan.evidence_requirements.sql_companies if ticker not in sql_companies
    ]
    missing_rag_companies = [
        ticker for ticker in plan.evidence_requirements.rag_companies if ticker not in rag_companies
    ]
    missing_metrics = _missing_metrics(plan, sql_rows)
    missing_metric_values = _missing_metric_values(plan, sql_rows)
    missing_periods = _missing_periods(plan, sql_rows)
    weak_document_themes = _weak_document_themes(plan, rag_results)

    warnings: list[str] = []
    if "structured" in plan.required_sources and not sql_rows:
        warnings.append("SQL evidence was required by the research plan but returned no rows.")
    if "unstructured" in plan.required_sources and not rag_results:
        warnings.append(
            "Document evidence was required by the research plan but retrieval returned no passages."
        )
    for ticker in missing_sql_companies:
        warnings.append(f"Missing SQL evidence for planned company {ticker}.")
    for ticker in missing_rag_companies:
        warnings.append(f"Missing document evidence for planned company {ticker}.")
    for metric in missing_metrics:
        warnings.append(f"Missing planned metric {metric}.")
    for ticker, metrics in missing_metric_values.items():
        metric_list = ", ".join(metrics)
        warnings.append(f"{ticker} has null values for planned metric(s): {metric_list}.")
    for ticker, count in missing_periods.items():
        expected = plan.evidence_requirements.minimum_quarters_per_company
        warnings.append(f"{ticker} has {count} quarters of SQL evidence; expected {expected}.")
    for theme in weak_document_themes:
        warnings.append(f"Weak document evidence for planned theme: {theme}.")

    needs_retry = bool(missing_rag_companies or weak_document_themes)
    passed = not warnings

    return {
        "passed": passed,
        "missing_sql_companies": missing_sql_companies,
        "missing_rag_companies": missing_rag_companies,
        "missing_metrics": missing_metrics,
        "missing_metric_values": missing_metric_values,
        "missing_periods": missing_periods,
        "weak_document_themes": weak_document_themes,
        "warnings": warnings,
        "needs_retry": needs_retry,
    }


def _missing_metrics(plan: ResearchPlan, sql_rows: list[dict]) -> list[str]:
    if not sql_rows:
        return plan.required_metrics if "structured" in plan.required_sources else []
    missing = []
    for metric in plan.required_metrics:
        if metric not in sql_rows[0]:
            missing.append(metric)
    return missing


def _missing_metric_values(plan: ResearchPlan, sql_rows: list[dict]) -> dict[str, list[str]]:
    missing_values: dict[str, set[str]] = {}
    for row in sql_rows:
        ticker = row.get("ticker")
        if not ticker:
            continue
        for metric in plan.required_metrics:
            if metric in row and row.get(metric) is None:
                missing_values.setdefault(ticker, set()).add(metric)
    return {ticker: sorted(metrics) for ticker, metrics in missing_values.items()}


def _missing_periods(plan: ResearchPlan, sql_rows: list[dict]) -> dict[str, int]:
    expected = plan.evidence_requirements.minimum_quarters_per_company
    if expected is None:
        return {}

    counts: dict[str, set[str]] = {}
    for row in sql_rows:
        ticker = row.get("ticker")
        period_end = row.get("period_end")
        if ticker and period_end:
            counts.setdefault(ticker, set()).add(str(period_end))

    missing = {}
    for ticker in plan.evidence_requirements.sql_companies:
        count = len(counts.get(ticker, set()))
        if count < expected:
            missing[ticker] = count
    return missing


def _weak_document_themes(plan: ResearchPlan, rag_results: list[dict]) -> list[str]:
    if not rag_results or not plan.document_themes:
        return plan.document_themes if "unstructured" in plan.required_sources else []

    combined_text = " ".join(str(item.get("text", "")).lower() for item in rag_results)
    weak = []
    for theme in plan.document_themes:
        theme_tokens = [token for token in theme.lower().split() if len(token) > 2]
        if theme_tokens and not any(token in combined_text for token in theme_tokens):
            weak.append(theme)
    return weak
