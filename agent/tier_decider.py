from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

from agent.company_catalog import alias_to_ticker_map, extract_ticker_mentions, normalize_alias
from agent.router import classify_question, classify_question_fallback

TierName = Literal["sql_fast", "rag_fast", "hybrid_fast", "deep_research"]
RouteName = Literal["sql", "rag", "hybrid"]

KNOWN_COMPANY_TICKERS = {
    "microsoft": "MSFT",
    "msft": "MSFT",
    "nvidia": "NVDA",
    "nvda": "NVDA",
    "apple": "AAPL",
    "aapl": "AAPL",
    "amazon": "AMZN",
    "amzn": "AMZN",
    "google": "GOOGL",
    "alphabet": "GOOGL",
    "googl": "GOOGL",
    "meta": "META",
    "meta platforms": "META",
    "tesla": "TSLA",
    "tsla": "TSLA",
}

METRIC_TERMS = {
    "revenue",
    "sales",
    "margin",
    "capex",
    "capital expenditure",
    "capital expenditures",
    "r&d",
    "rd",
    "growth",
    "operating income",
    "gross margin",
}
QUALITATIVE_TERMS = {
    "risk",
    "risks",
    "strategy",
    "management",
    "commentary",
    "driver",
    "drivers",
    "drove",
    "why",
    "explain",
    "ai",
    "artificial intelligence",
    "demand",
    "estimate",
    "forecast",
    "guidance",
    "projection",
}
COMPARATIVE_TERMS = {"compare", "comparison", "versus", "vs", "against"}


class TierDecision(BaseModel):
    tier: TierName
    route: RouteName
    companies: list[str]
    time_window: str | None = None
    needs_validation: bool
    max_retries: int
    rationale: str


def extract_companies(question: str) -> list[str]:
    normalized = normalize_alias(question)
    tickers: list[str] = extract_ticker_mentions(question)

    for alias, ticker in _company_mapping().items():
        pattern = rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])"
        if re.search(pattern, normalized) and ticker not in tickers:
            tickers.append(ticker)

    return tickers


def decide_tier(question: str) -> TierDecision:
    companies = extract_companies(question)
    normalized = question.lower()
    metric_hits = _hits(normalized, METRIC_TERMS)
    qualitative_hits = _hits(normalized, QUALITATIVE_TERMS)
    comparative_hits = _hits(normalized, COMPARATIVE_TERMS)
    multi_company = len(companies) > 1
    simple_metric_comparison = (
        multi_company and bool(metric_hits) and not qualitative_hits and bool(comparative_hits)
    )

    if comparative_hits and any(
        term in qualitative_hits for term in {"driver", "drivers", "why", "ai"}
    ):
        return _decision(
            "deep_research",
            "hybrid",
            companies,
            f"comparative driver-analysis terms: {', '.join(sorted(comparative_hits | qualitative_hits))}",
        )

    if multi_company and not simple_metric_comparison:
        return _decision(
            "deep_research",
            "hybrid",
            companies,
            "multi-company question needs bounded deep research",
        )

    if metric_hits and not qualitative_hits:
        return _decision(
            "sql_fast",
            "sql",
            companies,
            f"metric-only terms: {', '.join(sorted(metric_hits))}",
        )

    if qualitative_hits and not metric_hits:
        route: RouteName = "rag"
        return _decision(
            "rag_fast",
            route,
            companies,
            f"qualitative filing terms: {', '.join(sorted(qualitative_hits))}",
        )

    if metric_hits and qualitative_hits:
        return _decision(
            "hybrid_fast",
            "hybrid",
            companies,
            "question mixes metrics with narrative drivers/commentary",
        )

    try:
        route_decision = classify_question(question)
    except Exception as exc:
        route_decision = classify_question_fallback(question, error=exc)

    route = _as_route(route_decision.route)
    tier: TierName = (
        "hybrid_fast" if route == "hybrid" else "sql_fast" if route == "sql" else "rag_fast"
    )
    return _decision(tier, route, companies, "; ".join(route_decision.reasons))


def _company_mapping() -> dict[str, str]:
    mapping = {normalize_alias(alias): ticker for alias, ticker in KNOWN_COMPANY_TICKERS.items()}
    try:
        mapping.update(alias_to_ticker_map())
    except Exception:
        pass
    return mapping


def _hits(question: str, terms: set[str]) -> set[str]:
    return {term for term in terms if term in question}


def _as_route(route: str) -> RouteName:
    return route if route in {"sql", "rag", "hybrid"} else "hybrid"  # type: ignore[return-value]


def _decision(
    tier: TierName, route: RouteName, companies: list[str], rationale: str
) -> TierDecision:
    return TierDecision(
        tier=tier,
        route=route,
        companies=companies,
        time_window=None,
        needs_validation=tier in {"rag_fast", "hybrid_fast", "deep_research"},
        max_retries=2 if tier == "deep_research" else 0,
        rationale=rationale,
    )
