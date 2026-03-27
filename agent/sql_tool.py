from __future__ import annotations


SAMPLE_METRICS = [
    {
        "ticker": "MSFT",
        "period_end": "2025-12-31",
        "revenue_growth_yoy": 0.13,
        "operating_margin": 0.45,
        "capex_pct_revenue": 0.18,
        "rd_pct_revenue": 0.13,
    },
    {
        "ticker": "GOOGL",
        "period_end": "2025-12-31",
        "revenue_growth_yoy": 0.11,
        "operating_margin": 0.31,
        "capex_pct_revenue": 0.16,
        "rd_pct_revenue": 0.15,
    },
    {
        "ticker": "AMZN",
        "period_end": "2025-12-31",
        "revenue_growth_yoy": 0.10,
        "operating_margin": 0.12,
        "capex_pct_revenue": 0.12,
        "rd_pct_revenue": 0.11,
    },
]


def generate_sql(question: str) -> str:
    normalized = question.lower()
    if "highest operating margin" in normalized:
        return "SELECT ticker, operating_margin FROM v_company_period_metrics ORDER BY operating_margin DESC LIMIT 1;"
    if "capex" in normalized:
        return "SELECT ticker, period_end, capex_pct_revenue FROM v_company_period_metrics ORDER BY period_end DESC;"
    return "SELECT ticker, period_end, revenue_growth_yoy, operating_margin, capex_pct_revenue, rd_pct_revenue FROM v_company_period_metrics;"


def run_sql(question: str) -> dict:
    return {"sql": generate_sql(question), "rows": SAMPLE_METRICS}
