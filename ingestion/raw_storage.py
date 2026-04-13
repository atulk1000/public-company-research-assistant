from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_SEC_ROOT = PROJECT_ROOT / "data" / "raw" / "sec"


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_json(payload: dict, path: Path) -> Path:
    ensure_directory(path.parent)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def save_text(text: str, path: Path) -> Path:
    ensure_directory(path.parent)
    path.write_text(text, encoding="utf-8")
    return path


def company_directory(ticker: str) -> Path:
    return ensure_directory(RAW_SEC_ROOT / ticker.upper())


def submissions_path(ticker: str) -> Path:
    return company_directory(ticker) / "submissions.json"


def company_facts_path(ticker: str) -> Path:
    return company_directory(ticker) / "companyfacts.json"


def filing_html_path(ticker: str, filing_date: str, form_type: str, accession_no: str) -> Path:
    safe_form = form_type.replace("/", "-")
    return company_directory(ticker) / "filings" / f"{filing_date}_{safe_form}_{accession_no}.html"
