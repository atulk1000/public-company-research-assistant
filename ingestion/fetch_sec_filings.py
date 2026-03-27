from __future__ import annotations

import httpx


def submissions_url(cik: str) -> str:
    return f"https://data.sec.gov/submissions/CIK{cik}.json"


def fetch_submissions(cik: str) -> dict:
    with httpx.Client(timeout=30.0, headers={"User-Agent": "public-company-research-assistant"}) as client:
        response = client.get(submissions_url(cik))
        response.raise_for_status()
        return response.json()


def extract_recent_filings(payload: dict) -> list[dict]:
    recent = payload.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accession_numbers = recent.get("accessionNumber", [])
    filing_dates = recent.get("filingDate", [])
    return [
        {"form_type": form, "accession_no": accession, "filing_date": filing_date}
        for form, accession, filing_date in zip(forms, accession_numbers, filing_dates, strict=False)
        if form in {"10-K", "10-Q"}
    ]
