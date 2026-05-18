from __future__ import annotations

from agent.state import AgentState


def validate_evidence_coverage(state: AgentState) -> dict:
    route = state.route or "hybrid"
    companies = state.companies
    needs_sql = route in {"sql", "hybrid"}
    needs_rag = route in {"rag", "hybrid"}

    sql_rows = []
    if isinstance(state.sql_results, dict):
        sql_rows = state.sql_results.get("rows") or []

    rag_results = state.rag_results or []
    sql_companies = {row.get("ticker") for row in sql_rows if row.get("ticker")}
    rag_companies = {
        item.get("metadata", {}).get("ticker")
        for item in rag_results
        if item.get("metadata", {}).get("ticker")
    }

    missing_sql_companies = [
        ticker for ticker in companies if needs_sql and ticker not in sql_companies
    ]
    missing_rag_companies = [
        ticker for ticker in companies if needs_rag and ticker not in rag_companies
    ]

    warnings: list[str] = []
    if needs_sql and not sql_rows:
        warnings.append("SQL evidence was required but returned no rows.")
    if needs_rag and not rag_results:
        warnings.append("Document evidence was required but retrieval returned no passages.")
    if needs_rag:
        missing_labels = [
            item
            for item in rag_results
            if not item.get("source")
            or not item.get("metadata", {}).get("doc_type")
            or not item.get("metadata", {}).get("doc_date")
        ]
        if missing_labels:
            warnings.append("Some document evidence is missing citation metadata.")
    for ticker in missing_sql_companies:
        warnings.append(f"Missing SQL evidence for {ticker}.")
    for ticker in missing_rag_companies:
        warnings.append(f"Missing document evidence for {ticker}.")

    needs_retry = bool(missing_rag_companies or (needs_rag and not rag_results))
    passed = not warnings and not missing_sql_companies and not missing_rag_companies
    return {
        "passed": passed,
        "missing_sql_companies": missing_sql_companies,
        "missing_rag_companies": missing_rag_companies,
        "warnings": warnings,
        "needs_retry": needs_retry,
    }
