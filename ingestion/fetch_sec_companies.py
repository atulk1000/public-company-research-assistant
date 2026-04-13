from __future__ import annotations

import httpx

from ingestion.sec_api import sec_headers

SEC_COMPANIES_URL = "https://www.sec.gov/files/company_tickers.json"


def fetch_company_index() -> dict:
    """Fetch the SEC ticker index used to map ticker symbols to CIKs."""
    with httpx.Client(timeout=30.0, headers=sec_headers()) as client:
        response = client.get(SEC_COMPANIES_URL)
        response.raise_for_status()
        return response.json()


def normalize_company_index(payload: dict) -> list[dict]:
    companies = []
    for record in payload.values():
        companies.append(
            {
                "cik": str(record["cik_str"]).zfill(10),
                "ticker": record["ticker"].upper(),
                "name": record["title"],
            }
        )
    return companies
