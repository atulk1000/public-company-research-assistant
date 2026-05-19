from __future__ import annotations

import re
from typing import Any

import psycopg
from psycopg.rows import dict_row

from agent.company_resolver import resolve_company
from agent.hybrid_tool import answer_question
from agent.rag_tool import retrieve_evidence
from app.config import get_settings
from ingestion.live_ingest import run_live_ingestion
from ingestion.source_registry import (
    STRUCTURED_SOURCE_LABELS,
    UNSTRUCTURED_DOCUMENT_FORMS,
    UNSTRUCTURED_SOURCE_LABELS,
)
from mcp_server.config import ALLOWED_METRICS, LIMITS, METRIC_DESCRIPTIONS
from mcp_server.logging import emit_tool_log

BASE_METRIC_COLUMNS = ("ticker", "name", "period_end", "fiscal_year", "fiscal_quarter", "currency")
TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")


def get_connection():
    return psycopg.connect(get_settings().database_url, row_factory=dict_row)


def _normalize_ticker(ticker: str) -> str:
    normalized = ticker.strip().upper()
    if not TICKER_RE.match(normalized):
        raise ValueError(f"Invalid ticker: {ticker}")
    return normalized


def _normalize_tickers(tickers: list[str]) -> list[str]:
    normalized = [_normalize_ticker(ticker) for ticker in tickers]
    unique = list(dict.fromkeys(normalized))
    if not unique:
        raise ValueError("At least one ticker is required.")
    if len(unique) > LIMITS.max_companies_per_call:
        raise ValueError(
            f"Too many companies requested. Maximum is {LIMITS.max_companies_per_call}."
        )
    return unique


def _normalize_metrics(metrics: list[str] | None) -> list[str]:
    requested = metrics or ["revenue", "revenue_growth_yoy", "operating_margin"]
    normalized = [metric.strip().lower() for metric in requested]
    invalid = [metric for metric in normalized if metric not in ALLOWED_METRICS]
    if invalid:
        allowed = ", ".join(sorted(ALLOWED_METRICS))
        raise ValueError(
            f"Unsupported metric(s): {', '.join(invalid)}. Allowed metrics: {allowed}."
        )
    return list(dict.fromkeys(normalized))


def _normalize_limit(limit: int, maximum: int) -> int:
    return max(1, min(int(limit), maximum))


def _period_filter(periods: str | list[str] | None) -> tuple[str, list[Any], int]:
    if periods is None or periods == "latest":
        return "", [], 1
    if periods == "last_four_quarters":
        return "", [], 4
    if isinstance(periods, str):
        period_values = [periods]
    else:
        period_values = periods
    if not period_values:
        return "", [], 1
    return (
        "AND period_end = ANY(%s::date[])",
        [period_values],
        min(len(period_values), LIMITS.max_metric_rows),
    )


def _metric_rows(
    tickers: list[str],
    metrics: list[str],
    periods: str | list[str] | None,
    fiscal_quarter_only: bool,
    limit: int,
) -> list[dict[str, Any]]:
    period_clause, period_params, period_limit = _period_filter(periods)
    row_limit = _normalize_limit(max(limit, period_limit * len(tickers)), LIMITS.max_metric_rows)
    columns = [*BASE_METRIC_COLUMNS, *metrics]
    quoted_columns = ", ".join(columns)
    quarter_clause = "AND fiscal_quarter LIKE 'Q%'" if fiscal_quarter_only else ""
    sql = f"""
        WITH ranked_metrics AS (
            SELECT
                {quoted_columns},
                ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY period_end DESC) AS metric_rank
            FROM v_company_period_metrics
            WHERE ticker = ANY(%s)
            {quarter_clause}
            {period_clause}
        )
        SELECT {quoted_columns}
        FROM ranked_metrics
        WHERE metric_rank <= %s
        ORDER BY ticker, period_end DESC
        LIMIT %s;
    """
    params: list[Any] = [tickers, *period_params, period_limit, row_limit]
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]


def _metric_citations(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    citations = []
    for row in rows:
        period_end = str(row.get("period_end", "unknown"))
        ticker = row.get("ticker", "UNKNOWN")
        citations.append(
            {
                "id": f"SQL:{ticker}:{period_end}",
                "ticker": ticker,
                "period_end": period_end,
            }
        )
    return citations


def query_financial_metrics(
    ticker: str,
    metrics: list[str] | None = None,
    periods: str | list[str] | None = "latest",
    fiscal_quarter_only: bool = True,
) -> dict[str, Any]:
    tool = "query_financial_metrics"
    normalized_ticker = _normalize_ticker(ticker)
    normalized_metrics = _normalize_metrics(metrics)
    emit_tool_log(tool, "start", {"ticker": normalized_ticker, "metrics": normalized_metrics})
    rows = _metric_rows(
        [normalized_ticker],
        normalized_metrics,
        periods,
        fiscal_quarter_only,
        limit=LIMITS.max_metric_rows,
    )
    result = {
        "rows": rows,
        "citations": _metric_citations(rows),
        "warnings": [] if rows else [f"No structured metric rows found for {normalized_ticker}."],
    }
    emit_tool_log(tool, "finish", {"row_count": len(rows)})
    return result


def compare_company_metrics(
    tickers: list[str],
    metrics: list[str] | None = None,
    periods: str | list[str] | None = "last_four_quarters",
    fiscal_quarter_only: bool = True,
) -> dict[str, Any]:
    tool = "compare_company_metrics"
    normalized_tickers = _normalize_tickers(tickers)
    normalized_metrics = _normalize_metrics(metrics)
    emit_tool_log(tool, "start", {"tickers": normalized_tickers, "metrics": normalized_metrics})
    rows = _metric_rows(
        normalized_tickers,
        normalized_metrics,
        periods,
        fiscal_quarter_only,
        limit=LIMITS.max_metric_rows,
    )
    missing = sorted(set(normalized_tickers) - {row["ticker"] for row in rows})
    result = {
        "rows": rows,
        "citations": _metric_citations(rows),
        "warnings": [f"No structured metric rows found for {ticker}." for ticker in missing],
    }
    emit_tool_log(tool, "finish", {"row_count": len(rows), "missing": missing})
    return result


def _filter_evidence(
    evidence: list[dict[str, Any]], ticker: str, filing_types: list[str] | None, limit: int
) -> list[dict[str, Any]]:
    normalized_forms = {form.upper() for form in filing_types or []}
    filtered = []
    for item in evidence:
        metadata = item.get("metadata") or {}
        if metadata.get("ticker") != ticker:
            continue
        if normalized_forms and str(metadata.get("doc_type", "")).upper() not in normalized_forms:
            continue
        filtered.append(item)
        if len(filtered) >= limit:
            break
    return filtered


def retrieve_filing_context(
    ticker: str,
    topic: str,
    filing_types: list[str] | None = None,
    limit: int = 6,
) -> dict[str, Any]:
    tool = "retrieve_filing_context"
    normalized_ticker = _normalize_ticker(ticker)
    normalized_limit = _normalize_limit(limit, LIMITS.max_retrieval_chunks)
    query = f"{topic} {' '.join(filing_types or [])}".strip()
    emit_tool_log(
        tool,
        "start",
        {"ticker": normalized_ticker, "topic": topic, "limit": normalized_limit},
    )
    evidence = retrieve_evidence(
        query,
        top_k=normalized_limit,
        requested_tickers=[normalized_ticker],
    )
    filtered = _filter_evidence(evidence, normalized_ticker, filing_types, normalized_limit)
    result = {
        "evidence": filtered,
        "warnings": [] if filtered else [f"No filing evidence found for {normalized_ticker}."],
    }
    emit_tool_log(tool, "finish", {"evidence_count": len(filtered)})
    return result


def refresh_company_data(
    ticker: str,
    required_sources: list[str] | None = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    tool = "refresh_company_data"
    normalized_ticker = _normalize_ticker(ticker)
    required = required_sources or ["structured", "unstructured"]
    allowed_sources = {"structured", "unstructured"}
    invalid = sorted(set(required) - allowed_sources)
    if invalid:
        raise ValueError("required_sources can only contain structured and unstructured.")

    emit_tool_log(
        tool,
        "start",
        {
            "ticker": normalized_ticker,
            "required_sources": required,
            "force_refresh": force_refresh,
        },
    )
    resolution = resolve_company(normalized_ticker, normalized_ticker)
    if resolution.status != "resolved":
        return {
            "status": resolution.status,
            "message": getattr(resolution, "message", "Company could not be resolved."),
        }
    result = run_live_ingestion(
        resolution,
        required_sources=required,
        force_refresh=force_refresh,
    )
    payload = {
        "status": "success",
        "ticker": result.ticker,
        "company_name": result.company_name,
        "used_cache": result.used_cache,
        "structured_counts": result.structured_counts,
        "document_counts": result.document_counts,
        "embedding_counts": result.embedding_counts,
        "freshness": result.freshness,
    }
    emit_tool_log(tool, "finish", {"ticker": result.ticker, "used_cache": result.used_cache})
    return payload


def answer_financial_question(question: str, live_analysis: bool = False) -> dict[str, Any]:
    tool = "answer_financial_question"
    emit_tool_log(tool, "start", {"live_analysis": live_analysis})
    result = answer_question(question, live_analysis=live_analysis, return_trace=True)
    emit_tool_log(tool, "finish", {"status": result.get("status"), "route": result.get("route")})
    return result


def loaded_companies_resource() -> dict[str, Any]:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT ticker, name, cik
                FROM companies
                ORDER BY ticker;
                """)
            rows = [dict(row) for row in cursor.fetchall()]
    return {"companies": rows, "count": len(rows)}


def metrics_schema_resource() -> dict[str, Any]:
    return {
        "view": "v_company_period_metrics",
        "dimensions": list(BASE_METRIC_COLUMNS),
        "metrics": [
            {"name": metric, "description": METRIC_DESCRIPTIONS[metric]}
            for metric in sorted(ALLOWED_METRICS)
        ],
        "limits": {"max_rows": LIMITS.max_metric_rows},
    }


def sources_policy_resource() -> dict[str, Any]:
    return {
        "policy": "Official SEC-filed data only.",
        "structured_sources": list(STRUCTURED_SOURCE_LABELS),
        "unstructured_sources": list(UNSTRUCTURED_SOURCE_LABELS),
        "supported_document_forms": sorted(UNSTRUCTURED_DOCUMENT_FORMS),
    }


def freshness_resource() -> dict[str, Any]:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT
                    c.ticker,
                    c.name,
                    f.structured_refreshed_at::text AS structured_refreshed_at,
                    f.documents_refreshed_at::text AS documents_refreshed_at,
                    f.embeddings_refreshed_at::text AS embeddings_refreshed_at
                FROM companies c
                LEFT JOIN company_data_freshness f ON f.company_id = c.company_id
                ORDER BY c.ticker;
                """)
            rows = [dict(row) for row in cursor.fetchall()]
    return {"freshness": rows}


def capabilities_resource() -> dict[str, Any]:
    return {
        "tools": [
            "query_financial_metrics",
            "retrieve_filing_context",
            "refresh_company_data",
            "compare_company_metrics",
            "answer_financial_question",
        ],
        "resources": [
            "companies://loaded",
            "metrics://schema",
            "sources://sec-policy",
            "freshness://companies",
            "agent://capabilities",
        ],
        "limits": LIMITS.__dict__,
        "guardrails": [
            "No arbitrary SQL execution.",
            "Company and metric inputs are validated against allowlists.",
            "Live refresh is explicit and one company per refresh call.",
            "Final answers are scoped to US public-company financial research.",
        ],
    }
