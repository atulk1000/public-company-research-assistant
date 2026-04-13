from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from agent.company_catalog import alias_variants, normalize_alias
from app.config import get_settings
from ingestion.fetch_sec_companies import fetch_company_index, normalize_company_index


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_PATH = PROJECT_ROOT / "data" / "reference" / "sec" / "company_tickers.json"
class CompanyCandidate(BaseModel):
    ticker: str
    name: str
    cik: str


class ResolvedCompany(BaseModel):
    status: Literal["resolved"]
    ticker: str
    company_name: str
    cik: str


class AmbiguousCompanyMatch(BaseModel):
    status: Literal["ambiguous"]
    message: str
    candidates: list[CompanyCandidate]


class CompanyNotFound(BaseModel):
    status: Literal["not_found"]
    message: str


def ensure_reference_directory() -> None:
    REFERENCE_PATH.parent.mkdir(parents=True, exist_ok=True)


def read_reference_cache() -> list[dict] | None:
    if not REFERENCE_PATH.exists():
        return None

    modified_at = datetime.fromtimestamp(REFERENCE_PATH.stat().st_mtime, tz=timezone.utc)
    ttl = timedelta(hours=get_settings().sec_reference_cache_hours)
    if datetime.now(timezone.utc) - modified_at > ttl:
        return None

    return json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))


def write_reference_cache(companies: list[dict]) -> None:
    ensure_reference_directory()
    REFERENCE_PATH.write_text(json.dumps(companies, indent=2), encoding="utf-8")


@lru_cache(maxsize=1)
def load_reference_companies() -> list[dict]:
    cached = read_reference_cache()
    if cached is not None:
        return cached

    companies = normalize_company_index(fetch_company_index())
    write_reference_cache(companies)
    return companies


def refresh_reference_companies() -> list[dict]:
    load_reference_companies.cache_clear()
    return load_reference_companies()


def candidate_aliases(record: dict) -> set[str]:
    aliases = {normalize_alias(record["ticker"])}
    aliases.update(alias_variants(record["name"]))
    return aliases


def resolve_candidates(company_name: str | None, ticker: str | None, clarification: str | None = None) -> list[dict]:
    companies = load_reference_companies()
    return resolve_candidates_from_records(companies, company_name, ticker, clarification=clarification)


def resolve_candidates_from_records(companies: list[dict], company_name: str | None, ticker: str | None, clarification: str | None = None) -> list[dict]:
    normalized_ticker = ticker.strip().upper() if ticker else None
    search_terms = [normalize_alias(value) for value in [company_name, clarification] if value]
    search_terms = [term for term in search_terms if term]

    if normalized_ticker:
        exact_ticker_matches = [company for company in companies if company["ticker"].upper() == normalized_ticker]
        if exact_ticker_matches:
            return exact_ticker_matches

    if not search_terms:
        return []

    exact_matches: list[dict] = []
    partial_matches: list[dict] = []
    for company in companies:
        aliases = candidate_aliases(company)
        if any(term in aliases for term in search_terms):
            exact_matches.append(company)
            continue

        normalized_name = normalize_alias(company["name"])
        if any(term in normalized_name or normalized_name in term for term in search_terms if len(term) >= 3):
            partial_matches.append(company)

    return exact_matches or partial_matches


def resolve_company(company_name: str | None, ticker: str | None, clarification: str | None = None) -> ResolvedCompany | AmbiguousCompanyMatch | CompanyNotFound:
    candidates = resolve_candidates(company_name, ticker, clarification=clarification)

    if not candidates:
        return CompanyNotFound(
            status="not_found",
            message="Sorry, we could not confidently identify the company. Please check that it is a valid US-listed public company.",
        )

    if len(candidates) == 1:
        candidate = candidates[0]
        return ResolvedCompany(
            status="resolved",
            ticker=candidate["ticker"],
            company_name=candidate["name"],
            cik=candidate["cik"],
        )

    shortlist = [
        CompanyCandidate(ticker=candidate["ticker"], name=candidate["name"], cik=candidate["cik"])
        for candidate in candidates[:5]
    ]
    return AmbiguousCompanyMatch(
        status="ambiguous",
        message="I found more than one possible company match. Please clarify with the ticker or full company name.",
        candidates=shortlist,
    )
