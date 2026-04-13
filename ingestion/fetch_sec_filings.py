from __future__ import annotations

import httpx

from ingestion.sec_api import sec_headers
from ingestion.source_registry import is_supported_document_form


def submissions_url(cik: str) -> str:
    return f"https://data.sec.gov/submissions/CIK{cik}.json"


def fetch_submissions(cik: str) -> dict:
    with httpx.Client(timeout=30.0, headers=sec_headers()) as client:
        response = client.get(submissions_url(cik))
        response.raise_for_status()
        return response.json()


def extract_recent_filings(payload: dict) -> list[dict]:
    recent = payload.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accession_numbers = recent.get("accessionNumber", [])
    filing_dates = recent.get("filingDate", [])
    report_dates = recent.get("reportDate", [])
    primary_documents = recent.get("primaryDocument", [])
    return [
        {
            "form_type": form,
            "accession_no": accession,
            "filing_date": filing_date,
            "report_date": report_date,
            "primary_document": primary_document,
        }
        for form, accession, filing_date, report_date, primary_document in zip(
            forms,
            accession_numbers,
            filing_dates,
            report_dates,
            primary_documents,
            strict=False,
        )
        if is_supported_document_form(form)
    ]
