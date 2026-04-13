from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import os
from pathlib import Path
import sys
import time

import psycopg
from psycopg.rows import dict_row

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ingestion.fetch_company_facts import extract_usd_facts, fetch_company_facts
from ingestion.fetch_sec_filings import extract_recent_filings, fetch_submissions
from ingestion.raw_storage import company_facts_path, save_json, submissions_path
from ingestion.source_registry import is_supported_currency_unit, is_supported_structured_form


REQUEST_PAUSE_SECONDS = 0.25

CONCEPT_ALIASES: dict[str, list[str]] = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ],
    "gross_profit": ["GrossProfit"],
    "operating_income": ["OperatingIncomeLoss"],
    "r_and_d": [
        "ResearchAndDevelopmentExpense",
        "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
    ],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PropertyPlantAndEquipmentAdditions",
    ],
    "operating_cash_flow": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
    "share_based_comp": [
        "ShareBasedCompensation",
        "AllocatedShareBasedCompensationExpense",
    ],
}

TARGET_CONCEPTS = {concept for aliases in CONCEPT_ALIASES.values() for concept in aliases}


@dataclass
class CompanyRecord:
    company_id: int
    cik: str
    ticker: str
    name: str


@dataclass
class IngestionSettings:
    database_url: str
    ticker_list: list[str]


def decimal_or_none(value: object) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def safe_ratio(numerator: Decimal | None, denominator: Decimal | None) -> Decimal | None:
    if numerator is None or denominator in {None, Decimal("0")}:
        return None
    return numerator / denominator


def filing_source_url(cik: str, accession_no: str, primary_document: str | None) -> str | None:
    if not primary_document:
        return None
    accession_path = accession_no.replace("-", "")
    cik_no_leading_zeroes = str(int(cik))
    return f"https://www.sec.gov/Archives/edgar/data/{cik_no_leading_zeroes}/{accession_path}/{primary_document}"


def get_connection():
    settings = load_settings()
    return psycopg.connect(settings.database_url, row_factory=dict_row)


def load_settings() -> IngestionSettings:
    target_tickers = os.getenv("TARGET_TICKERS", "MSFT,GOOGL,AMZN")
    return IngestionSettings(
        database_url=os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/company_assistant"),
        ticker_list=[ticker.strip().upper() for ticker in target_tickers.split(",") if ticker.strip()],
    )


def load_target_companies(conn: psycopg.Connection, tickers: list[str]) -> list[CompanyRecord]:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT company_id, cik, ticker, name
            FROM companies
            WHERE ticker = ANY(%s)
            ORDER BY ticker;
            """,
            (tickers,),
        )
        rows = cursor.fetchall()

    return [CompanyRecord(**row) for row in rows]


def clear_company_data(conn: psycopg.Connection, company_id: int) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            DELETE FROM document_chunks
            WHERE company_id = %s
               OR document_id IN (
                    SELECT document_id
                    FROM documents
                    WHERE company_id = %s
               );
            """,
            (company_id, company_id),
        )
        cursor.execute("DELETE FROM documents WHERE company_id = %s;", (company_id,))
        cursor.execute("DELETE FROM derived_metrics WHERE company_id = %s;", (company_id,))
        cursor.execute("DELETE FROM facts WHERE company_id = %s;", (company_id,))
        cursor.execute("DELETE FROM filings WHERE company_id = %s;", (company_id,))


def replace_filings(conn: psycopg.Connection, company: CompanyRecord, filings: list[dict]) -> dict[tuple[str, str], int]:
    with conn.cursor() as cursor:
        for filing in filings:
            cursor.execute(
                """
                INSERT INTO filings (
                    company_id,
                    accession_no,
                    form_type,
                    filing_date,
                    fiscal_year,
                    fiscal_quarter,
                    source_url
                )
                VALUES (%s, %s, %s, %s, NULL, NULL, %s);
                """,
                (
                    company.company_id,
                    filing["accession_no"],
                    filing["form_type"],
                    filing["filing_date"],
                    filing_source_url(company.cik, filing["accession_no"], filing.get("primary_document")),
                ),
            )

        cursor.execute(
            """
            SELECT filing_id, form_type, filing_date::text AS filing_date
            FROM filings
            WHERE company_id = %s;
            """,
            (company.company_id,),
        )
        rows = cursor.fetchall()

    return {(row["form_type"], row["filing_date"]): row["filing_id"] for row in rows}


def dedupe_facts(raw_rows: list[dict]) -> list[dict]:
    best_rows: dict[tuple[str, str | None, str, int | None, str | None, str], dict] = {}
    for row in raw_rows:
        if not is_supported_structured_form(row.get("form")):
            continue
        if not is_supported_currency_unit(row.get("unit")):
            continue
        if row.get("value") is None or not row.get("period_end"):
            continue

        key = (
            row["concept"],
            row.get("period_start"),
            row["period_end"],
            row.get("fiscal_year"),
            row.get("fiscal_quarter"),
            row["form"],
        )
        current = best_rows.get(key)
        if current is None or (row.get("filed") or "") > (current.get("filed") or ""):
            best_rows[key] = row

    return list(best_rows.values())


def replace_facts(
    conn: psycopg.Connection,
    company: CompanyRecord,
    filing_ids: dict[tuple[str, str], int],
    facts: list[dict],
) -> None:
    with conn.cursor() as cursor:
        for fact in facts:
            filing_id = filing_ids.get((fact["form"], fact.get("filed") or ""))
            cursor.execute(
                """
                INSERT INTO facts (
                    company_id,
                    filing_id,
                    taxonomy,
                    concept,
                    unit,
                    value,
                    period_start,
                    period_end,
                    fiscal_year,
                    fiscal_quarter,
                    filed_date
                )
                VALUES (%s, %s, 'us-gaap', %s, %s, %s, %s, %s, %s, %s, %s);
                """,
                (
                    company.company_id,
                    filing_id,
                    fact["concept"],
                    fact["unit"],
                    fact["value"],
                    fact.get("period_start"),
                    fact.get("period_end"),
                    fact.get("fiscal_year"),
                    fact.get("fiscal_quarter"),
                    fact.get("filed"),
                ),
            )


def concept_rank(metric_name: str, concept: str) -> int:
    return CONCEPT_ALIASES[metric_name].index(concept)


def parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def duration_days(row: dict) -> int | None:
    start = parse_iso_date(row.get("period_start"))
    end = parse_iso_date(row.get("period_end"))
    if start is None or end is None or end < start:
        return None
    return (end - start).days + 1


def preferred_duration_for_period(facts_for_period: list[dict], fiscal_quarter: str | None) -> int | None:
    durations = sorted({duration for row in facts_for_period if (duration := duration_days(row)) is not None})
    if not durations:
        return None

    normalized_quarter = (fiscal_quarter or "").upper()
    if normalized_quarter.startswith("Q"):
        quarter_like = [duration for duration in durations if 70 <= duration <= 120]
        if quarter_like:
            return min(quarter_like)

        usable = [duration for duration in durations if duration >= 45]
        if usable:
            return min(usable)

        return min(durations)

    annual_like = [duration for duration in durations if duration >= 300]
    if annual_like:
        return max(annual_like)

    return max(durations)


def preferred_unit_for_period(facts_for_period: list[dict], preferred_duration: int | None) -> str | None:
    duration_filtered = [
        row for row in facts_for_period
        if preferred_duration is None or duration_days(row) == preferred_duration
    ]
    if not duration_filtered:
        duration_filtered = facts_for_period

    revenue_candidates = []
    for row in duration_filtered:
        if row["concept"] in CONCEPT_ALIASES["revenue"] and is_supported_currency_unit(row.get("unit")):
            revenue_candidates.append(row)

    if revenue_candidates:
        ranked = sorted(
            revenue_candidates,
            key=lambda row: (
                concept_rank("revenue", row["concept"]),
                row.get("filed") or "",
            ),
        )
        return ranked[0]["unit"]

    unit_counts: dict[str, int] = {}
    for row in duration_filtered:
        unit = row.get("unit")
        if is_supported_currency_unit(unit):
            unit_counts[unit] = unit_counts.get(unit, 0) + 1

    if not unit_counts:
        return None
    return max(unit_counts.items(), key=lambda item: item[1])[0]


def build_metric_rows(company: CompanyRecord, facts: list[dict]) -> list[dict]:
    facts_by_period: dict[tuple[int, str, str | None], list[dict]] = {}

    for fact in facts:
        metric_name = None
        for candidate_metric, aliases in CONCEPT_ALIASES.items():
            if fact["concept"] in aliases:
                metric_name = candidate_metric
                break

        if metric_name is None:
            continue

        key = (
            company.company_id,
            fact["period_end"],
            fact.get("fiscal_quarter"),
        )
        facts_by_period.setdefault(key, []).append(fact)

    metric_rows: list[dict] = []
    for key, facts_for_period in facts_by_period.items():
        _, period_end, fiscal_quarter = key
        preferred_duration = preferred_duration_for_period(facts_for_period, fiscal_quarter)
        preferred_unit = preferred_unit_for_period(facts_for_period, preferred_duration)
        candidate_years = sorted(
            {
                fiscal_year
                for fact in facts_for_period
                if (fiscal_year := fact.get("fiscal_year")) is not None
            }
        )
        fiscal_year = candidate_years[0] if candidate_years else None

        bucket = {
            "company_id": company.company_id,
            "period_end": period_end,
            "fiscal_year": fiscal_year,
            "fiscal_quarter": fiscal_quarter,
            "currency": preferred_unit,
            "_alias_ranks": {},
        }

        for fact in facts_for_period:
            if preferred_duration is not None and duration_days(fact) != preferred_duration:
                continue
            if preferred_unit is not None and fact.get("unit") != preferred_unit:
                continue

            metric_name = None
            for candidate_metric, aliases in CONCEPT_ALIASES.items():
                if fact["concept"] in aliases:
                    metric_name = candidate_metric
                    break

            if metric_name is None:
                continue

            incoming_rank = concept_rank(metric_name, fact["concept"])
            existing_rank = bucket["_alias_ranks"].get(metric_name)
            if existing_rank is None or incoming_rank < existing_rank:
                bucket[metric_name] = decimal_or_none(fact["value"])
                bucket["_alias_ranks"][metric_name] = incoming_rank

        if bucket.get("revenue") is None:
            continue

        metric_rows.append(bucket)

    metric_rows.sort(key=lambda row: (row.get("fiscal_year") or 0, row["period_end"]))

    revenue_lookup: dict[tuple[int, str], Decimal] = {}
    for row in metric_rows:
        revenue = row.get("revenue")
        gross_profit = row.get("gross_profit")
        operating_income = row.get("operating_income")
        capex = row.get("capex")
        r_and_d = row.get("r_and_d")
        operating_cash_flow = row.get("operating_cash_flow")
        share_based_comp = row.get("share_based_comp")

        row["gross_margin"] = safe_ratio(gross_profit, revenue)
        row["operating_margin"] = safe_ratio(operating_income, revenue)
        row["capex_pct_revenue"] = safe_ratio(capex, revenue)
        row["rd_pct_revenue"] = safe_ratio(r_and_d, revenue)
        row["sbc_pct_revenue"] = safe_ratio(share_based_comp, revenue)

        free_cash_flow = None
        if operating_cash_flow is not None and capex is not None:
            free_cash_flow = operating_cash_flow - capex
        row["fcf_margin"] = safe_ratio(free_cash_flow, revenue)

        fiscal_year = row.get("fiscal_year")
        fiscal_quarter = row.get("fiscal_quarter") or ""
        previous_revenue = None
        if fiscal_year is not None:
            previous_revenue = revenue_lookup.get((fiscal_year - 1, fiscal_quarter))
        row["revenue_growth_yoy"] = safe_ratio(revenue - previous_revenue, previous_revenue) if revenue and previous_revenue else None
        if fiscal_year is not None and revenue is not None:
            revenue_lookup[(fiscal_year, fiscal_quarter)] = revenue

    for row in metric_rows:
        row.pop("_alias_ranks", None)

    return metric_rows


def replace_derived_metrics(conn: psycopg.Connection, company: CompanyRecord, metric_rows: list[dict]) -> None:
    with conn.cursor() as cursor:
        for row in metric_rows:
            cursor.execute(
                """
                INSERT INTO derived_metrics (
                    company_id,
                    period_end,
                    fiscal_year,
                    fiscal_quarter,
                    currency,
                    revenue,
                    revenue_growth_yoy,
                    gross_margin,
                    operating_margin,
                    fcf_margin,
                    capex,
                    capex_pct_revenue,
                    rd_pct_revenue,
                    sbc_pct_revenue
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """,
                (
                    row["company_id"],
                    row["period_end"],
                    row.get("fiscal_year"),
                    row.get("fiscal_quarter"),
                    row.get("currency"),
                    row.get("revenue"),
                    row.get("revenue_growth_yoy"),
                    row.get("gross_margin"),
                    row.get("operating_margin"),
                    row.get("fcf_margin"),
                    row.get("capex"),
                    row.get("capex_pct_revenue"),
                    row.get("rd_pct_revenue"),
                    row.get("sbc_pct_revenue"),
                ),
            )


def ingest_company(conn: psycopg.Connection, company: CompanyRecord) -> dict[str, int]:
    submissions = fetch_submissions(company.cik)
    save_json(submissions, submissions_path(company.ticker))
    time.sleep(REQUEST_PAUSE_SECONDS)
    company_facts = fetch_company_facts(company.cik)
    save_json(company_facts, company_facts_path(company.ticker))
    time.sleep(REQUEST_PAUSE_SECONDS)

    recent_filings = extract_recent_filings(submissions)
    raw_fact_rows = extract_usd_facts(company_facts, TARGET_CONCEPTS)
    fact_rows = dedupe_facts(raw_fact_rows)

    clear_company_data(conn, company.company_id)
    filing_ids = replace_filings(conn, company, recent_filings)
    replace_facts(conn, company, filing_ids, fact_rows)

    metric_rows = build_metric_rows(company, fact_rows)
    replace_derived_metrics(conn, company, metric_rows)

    return {
        "filings": len(recent_filings),
        "facts": len(fact_rows),
        "metric_rows": len(metric_rows),
    }


def print_summary(results: dict[str, dict[str, int]]) -> None:
    print("SEC ingestion complete.")
    for ticker, counts in results.items():
        print(
            f"- {ticker}: filings={counts['filings']}, "
            f"facts={counts['facts']}, derived_metrics={counts['metric_rows']}"
        )


def main() -> None:
    settings = load_settings()
    with get_connection() as conn:
        companies = load_target_companies(conn, settings.ticker_list)
        if not companies:
            raise RuntimeError("No target companies found. Apply db/seed.sql before running SEC ingestion.")

        results: dict[str, dict[str, int]] = {}
        for company in companies:
            print(f"Loading SEC data for {company.ticker} ({company.cik})...")
            results[company.ticker] = ingest_company(conn, company)
            conn.commit()

    print_summary(results)


if __name__ == "__main__":
    main()
