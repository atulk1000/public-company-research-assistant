from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
import os
import re
import sys
from typing import Literal

import psycopg
from psycopg.rows import dict_row
from pydantic import BaseModel

from agent.company_catalog import alias_to_ticker_map, available_tickers, company_context_lines, normalize_alias
from agent.openai_client import get_openai_client
from app.config import get_settings
from app.prompts import SQL_SYSTEM_PROMPT, SQL_USER_TEMPLATE

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/company_assistant"
ALLOWED_RELATIONS = {"v_company_period_metrics"}
FORBIDDEN_SQL_PATTERNS = (
    r"\binsert\b",
    r"\bupdate\b",
    r"\bdelete\b",
    r"\bdrop\b",
    r"\balter\b",
    r"\bcreate\b",
    r"\btruncate\b",
    r"\bgrant\b",
    r"\brevoke\b",
    r"\bcopy\b",
    r"\bcall\b",
    r"\brefresh\b",
    r"\bvacuum\b",
)
QUARTER_FILTER_PATTERNS = (
    "fiscal_quarter like 'q%'",
    'fiscal_quarter like "q%"',
    "fiscal_quarter in ('q1'",
    "fiscal_quarter in ('q2'",
    "fiscal_quarter in ('q3'",
    "fiscal_quarter in ('q4'",
    "fiscal_quarter = 'q1'",
    "fiscal_quarter = 'q2'",
    "fiscal_quarter = 'q3'",
    "fiscal_quarter = 'q4'",
    "fiscal_quarter <> 'fy'",
    "fiscal_quarter != 'fy'",
)

class SQLPlan(BaseModel):
    sql: str
    rationale: str


class SQLValidationError(ValueError):
    pass


def get_database_url() -> str:
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def get_connection():
    return psycopg.connect(get_database_url(), row_factory=dict_row)


def normalize_value(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def normalize_rows(rows: list[dict]) -> list[dict]:
    return [{key: normalize_value(value) for key, value in row.items()} for row in rows]


def extract_requested_tickers(question: str) -> list[str]:
    normalized = normalize_alias(question)
    tickers: list[str] = []
    for alias, ticker in alias_to_ticker_map().items():
        if not alias:
            continue
        alias_pattern = rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])"
        if re.search(alias_pattern, normalized) and ticker not in tickers:
            tickers.append(ticker)

    return tickers


def strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9_+-]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def extract_cte_names(sql: str) -> set[str]:
    names: set[str] = set()
    remaining = sql.strip()
    if not remaining.lower().startswith("with"):
        return names

    remaining = remaining[4:].strip()
    while remaining:
        match = re.match(r'([a-zA-Z_][\w]*)\s+as\s*\(', remaining, flags=re.IGNORECASE)
        if not match:
            break

        cte_name = match.group(1).lower()
        names.add(cte_name)
        index = match.end() - 1
        depth = 0
        while index < len(remaining):
            char = remaining[index]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    index += 1
                    break
            index += 1

        remaining = remaining[index:].lstrip()
        if remaining.startswith(","):
            remaining = remaining[1:].lstrip()
            continue
        break

    return names


def validate_sql(sql: str) -> str:
    cleaned = strip_code_fences(sql).strip()
    if not cleaned:
        raise SQLValidationError("The model returned an empty SQL query.")

    cleaned = cleaned.rstrip(";").strip()
    normalized = cleaned.lower()

    if ";" in cleaned:
        raise SQLValidationError("Only a single SQL statement is allowed.")
    if not (normalized.startswith("select") or normalized.startswith("with")):
        raise SQLValidationError("Only SELECT queries are allowed.")

    for pattern in FORBIDDEN_SQL_PATTERNS:
        if re.search(pattern, normalized):
            raise SQLValidationError(f"Rejected unsafe SQL containing pattern: {pattern}")

    relation_matches = re.findall(r"\b(?:from|join)\s+([a-zA-Z_][\w.]*)", normalized)
    if not relation_matches:
        raise SQLValidationError("SQL must reference at least one allowed relation.")

    referenced_relations = {match.split(".")[-1] for match in relation_matches}
    referenced_relations -= extract_cte_names(normalized)
    disallowed = referenced_relations - ALLOWED_RELATIONS
    if disallowed:
        allowed = ", ".join(sorted(ALLOWED_RELATIONS))
        raise SQLValidationError(f"SQL referenced unsupported relations: {', '.join(sorted(disallowed))}. Allowed: {allowed}.")

    return cleaned


def enforce_question_constraints(sql: str, question: str) -> str:
    normalized_question = question.lower()
    normalized_sql = sql.lower()

    if "quarter" in normalized_question and not any(pattern in normalized_sql for pattern in QUARTER_FILTER_PATTERNS):
        raise SQLValidationError(
            "Quarter-based questions must restrict results to quarterly rows where fiscal_quarter LIKE 'Q%'."
        )

    return sql


def generate_sql_fallback(question: str, error: Exception | None = None, requested_tickers: list[str] | None = None) -> dict:
    normalized = question.lower()
    requested_tickers = requested_tickers or extract_requested_tickers(question)
    quarterly_filter = "fiscal_quarter LIKE 'Q%'"

    rationale = "fallback rules over v_company_period_metrics"
    if error is not None:
        rationale = f"{rationale}; OpenAI error: {error}"

    if "highest operating margin" in normalized and "latest" in normalized:
        sql = """
            WITH latest_period AS (
                SELECT MAX(period_end) AS period_end
                FROM v_company_period_metrics
                WHERE fiscal_quarter LIKE 'Q%'
            )
            SELECT ticker, period_end, operating_margin
            FROM v_company_period_metrics
            WHERE period_end = (SELECT period_end FROM latest_period)
              AND fiscal_quarter LIKE 'Q%'
            ORDER BY operating_margin DESC
            LIMIT 1
        """.strip()
        return {"sql": sql, "rationale": rationale, "mode": "fallback_rules"}

    if "capex" in normalized:
        if requested_tickers:
            ticker_list = ", ".join(f"'{ticker}'" for ticker in requested_tickers)
            if "last four quarters" in normalized or "last 4 quarters" in normalized:
                sql = f"""
                    WITH ranked_periods AS (
                        SELECT
                            ticker,
                            period_end,
                            capex_pct_revenue,
                            revenue_growth_yoy,
                            operating_margin,
                            ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY period_end DESC) AS period_rank
                        FROM v_company_period_metrics
                        WHERE ticker IN ({ticker_list})
                          AND {quarterly_filter}
                    )
                    SELECT ticker, period_end, capex_pct_revenue, revenue_growth_yoy, operating_margin
                    FROM ranked_periods
                    WHERE period_rank <= 4
                    ORDER BY ticker, period_end DESC
                """.strip()
                return {"sql": sql, "rationale": rationale, "mode": "fallback_rules"}
            sql = f"""
                SELECT ticker, period_end, capex_pct_revenue, revenue_growth_yoy, operating_margin
                FROM v_company_period_metrics
                WHERE ticker IN ({ticker_list})
                  AND {quarterly_filter}
                ORDER BY period_end DESC
            """.strip()
            return {"sql": sql, "rationale": rationale, "mode": "fallback_rules"}

    if requested_tickers:
        ticker_list = ", ".join(f"'{ticker}'" for ticker in requested_tickers)
        sql = f"""
            SELECT ticker, period_end, revenue_growth_yoy, operating_margin, capex_pct_revenue, rd_pct_revenue
            FROM v_company_period_metrics
            WHERE ticker IN ({ticker_list})
              AND {quarterly_filter}
            ORDER BY period_end DESC
        """.strip()
        return {"sql": sql, "rationale": rationale, "mode": "fallback_rules"}

    sql = """
        SELECT ticker, period_end, revenue_growth_yoy, operating_margin, capex_pct_revenue, rd_pct_revenue
        FROM v_company_period_metrics
        WHERE fiscal_quarter LIKE 'Q%'
        ORDER BY period_end DESC
    """.strip()
    return {"sql": sql, "rationale": rationale, "mode": "fallback_rules"}


def generate_sql(question: str, requested_tickers: list[str] | None = None) -> dict:
    requested_tickers = requested_tickers or extract_requested_tickers(question)
    try:
        settings = get_settings()
        client = get_openai_client()
        response = client.responses.parse(
            model=settings.openai_model,
            reasoning={"effort": settings.openai_reasoning_effort},
            instructions=SQL_SYSTEM_PROMPT,
            input=SQL_USER_TEMPLATE.format(
                question=question,
                tickers=", ".join(available_tickers()) or "none loaded yet",
                companies="\n".join(company_context_lines()) or "- none loaded yet",
                focus_tickers=", ".join(requested_tickers) if requested_tickers else "none specified",
            ),
            text_format=SQLPlan,
        )
        plan = response.output_parsed
        validated_sql = validate_sql(plan.sql)
        constrained_sql = enforce_question_constraints(validated_sql, question)
        return {"sql": constrained_sql, "rationale": plan.rationale, "mode": "llm_generated"}
    except Exception as exc:
        return generate_sql_fallback(question, error=exc, requested_tickers=requested_tickers)


def run_query(sql: str) -> list[dict]:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql)
            rows = cursor.fetchall()
    return normalize_rows(rows)


def run_sql(question: str, requested_tickers: list[str] | None = None) -> dict:
    plan = generate_sql(question, requested_tickers=requested_tickers)
    rows = run_query(plan["sql"])
    return {
        "sql": plan["sql"],
        "generation_rationale": plan["rationale"],
        "rows": rows,
        "mode": plan.get("mode", "llm_generated"),
    }
