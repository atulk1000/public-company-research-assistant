from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class McpLimits:
    max_companies_per_call: int = 5
    max_metric_rows: int = 100
    max_retrieval_chunks: int = 10
    max_refresh_companies: int = 1
    max_answer_chunks: int = 8
    tool_timeout_seconds: int = 60
    refresh_timeout_seconds: int = 300


LIMITS = McpLimits()

ALLOWED_METRICS = {
    "revenue",
    "revenue_growth_yoy",
    "gross_margin",
    "operating_margin",
    "capex",
    "capex_pct_revenue",
    "rd_pct_revenue",
}

METRIC_DESCRIPTIONS = {
    "revenue": "Reported revenue for the period.",
    "revenue_growth_yoy": "Year-over-year revenue growth ratio.",
    "gross_margin": "Gross margin ratio.",
    "operating_margin": "Operating margin ratio.",
    "capex": "Capital expenditure for the period.",
    "capex_pct_revenue": "Capital expenditure as a ratio of revenue.",
    "rd_pct_revenue": "Research and development expense as a ratio of revenue.",
}
