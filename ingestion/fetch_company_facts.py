from __future__ import annotations

import httpx

from ingestion.sec_api import sec_headers


def company_facts_url(cik: str) -> str:
    return f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"


def fetch_company_facts(cik: str) -> dict:
    with httpx.Client(timeout=30.0, headers=sec_headers()) as client:
        response = client.get(company_facts_url(cik))
        response.raise_for_status()
        return response.json()


def extract_usd_facts(payload: dict, concept_names: set[str]) -> list[dict]:
    facts = payload.get("facts", {}).get("us-gaap", {})
    rows: list[dict] = []
    for concept_name in concept_names:
        concept = facts.get(concept_name, {})
        for unit_name, unit_rows in concept.get("units", {}).items():
            for row in unit_rows:
                rows.append(
                    {
                        "concept": concept_name,
                        "unit": unit_name,
                        "value": row.get("val"),
                        "period_start": row.get("start"),
                        "period_end": row.get("end"),
                        "fiscal_year": row.get("fy"),
                        "fiscal_quarter": row.get("fp"),
                        "filed": row.get("filed"),
                        "form": row.get("form"),
                    }
                )
    return rows
