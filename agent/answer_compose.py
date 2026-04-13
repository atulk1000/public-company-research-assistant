from __future__ import annotations

def format_percent(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


def format_period(value: str | None) -> str:
    if not value:
        return "unknown period"
    return value


def unique_period_rows(rows: list[dict]) -> list[dict]:
    seen: set[tuple[str | None, str | None]] = set()
    deduped: list[dict] = []
    for row in rows:
        key = (row.get("ticker"), row.get("period_end"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def compose_sql_answer(question: str, structured_evidence: dict) -> str:
    rows = unique_period_rows(structured_evidence.get("rows", []))
    if not rows:
        return "I could not find matching structured results in Postgres for that question."

    normalized = question.lower()
    if "compare" in normalized:
        latest_by_ticker: dict[str, dict] = {}
        for row in rows:
            ticker = row.get("ticker")
            if ticker and ticker not in latest_by_ticker:
                latest_by_ticker[ticker] = row

        comparisons = []
        for ticker, row in latest_by_ticker.items():
            comparisons.append(
                f"{ticker}: revenue growth {format_percent(row.get('revenue_growth_yoy'))}, "
                f"operating margin {format_percent(row.get('operating_margin'))}"
            )

        if comparisons:
            return "Latest structured comparison: " + "; ".join(comparisons) + "."

    if "highest operating margin" in normalized:
        top_row = rows[0]
        return (
            f"{top_row['ticker']} had the highest operating margin in the latest reported quarter, "
            f"at {format_percent(top_row.get('operating_margin'))} for the period ending {format_period(top_row.get('period_end'))}."
        )

    if "capex intensity" in normalized or "capex" in normalized:
        ticker = rows[0].get("ticker", "The company")
        recent_rows = rows[:4]
        latest = recent_rows[0]
        oldest = recent_rows[-1]
        trajectory = "increased" if (latest.get("capex_pct_revenue") or 0) > (oldest.get("capex_pct_revenue") or 0) else "decreased"
        series = ", ".join(
            f"{row.get('period_end')}: {format_percent(row.get('capex_pct_revenue'))}"
            for row in recent_rows
        )
        return (
            f"{ticker}'s capex intensity {trajectory} across the last four reported quarters. "
            f"It moved from {format_percent(oldest.get('capex_pct_revenue'))} on {format_period(oldest.get('period_end'))} "
            f"to {format_percent(latest.get('capex_pct_revenue'))} on {format_period(latest.get('period_end'))}. "
            f"Quarterly series: {series}."
        )

    return f"Structured analysis returned {len(rows)} matching metric rows from Postgres."


def compose_rag_answer(retrieved_evidence: list[dict]) -> str:
    if not retrieved_evidence:
        return "I could not find matching document evidence for that question."

    top_evidence = retrieved_evidence[0]
    ticker = top_evidence.get("metadata", {}).get("ticker", "The company")
    doc_type = top_evidence.get("metadata", {}).get("doc_type", "document")
    doc_date = top_evidence.get("metadata", {}).get("doc_date", "unknown date")
    return (
        f"The strongest retrieved evidence came from {ticker}'s {doc_type} dated {doc_date}. "
        f"Top passage: {top_evidence.get('text', '')}"
    )


def compose_hybrid_answer(question: str, structured_evidence: dict | None, retrieved_evidence: list[dict] | None) -> str:
    sql_summary = compose_sql_answer(question, structured_evidence or {"rows": []})
    rag_summary = compose_rag_answer(retrieved_evidence or [])
    return f"{sql_summary}\n\nDocument evidence: {rag_summary}"


def compose_answer(question: str, route: str, structured_evidence: dict | None, retrieved_evidence: list[dict] | None) -> str:
    if route == "sql" and structured_evidence:
        return compose_sql_answer(question, structured_evidence)
    if route == "rag" and retrieved_evidence is not None:
        return compose_rag_answer(retrieved_evidence)
    if route == "hybrid":
        return compose_hybrid_answer(question, structured_evidence, retrieved_evidence)
    return "I could not compose an answer from the available evidence."
