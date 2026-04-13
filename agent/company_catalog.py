from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_SEC_ROOT = PROJECT_ROOT / "data" / "raw" / "sec"


@dataclass(frozen=True)
class CompanyCatalogEntry:
    ticker: str
    name: str
    aliases: tuple[str, ...]


def normalize_alias(value: str) -> str:
    normalized = value.strip().lower()
    normalized = normalized.replace("&", " and ")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def alias_variants(name: str) -> set[str]:
    variants = {normalize_alias(name)}
    legal_suffixes = (
        " inc",
        " inc.",
        " corp",
        " corp.",
        " corporation",
        " ltd",
        " ltd.",
        " plc",
        " llc",
        " holdings",
        " holding",
        " company",
        " co",
        " co.",
    )

    changed = True
    while changed:
        changed = False
        current = list(variants)
        for value in current:
            for suffix in legal_suffixes:
                if value.endswith(suffix):
                    trimmed = value[: -len(suffix)].strip()
                    if trimmed and trimmed not in variants:
                        variants.add(trimmed)
                        changed = True
    return {variant for variant in variants if variant}


def load_submission_metadata(ticker_dir: Path) -> tuple[str, list[str]]:
    submissions_file = ticker_dir / "submissions.json"
    if not submissions_file.exists():
        return ticker_dir.name.upper(), [ticker_dir.name.upper()]

    data = json.loads(submissions_file.read_text(encoding="utf-8"))
    company_name = data.get("name") or ticker_dir.name.upper()
    tickers = [ticker.upper() for ticker in data.get("tickers", []) if ticker]
    if not tickers:
        tickers = [ticker_dir.name.upper()]
    return company_name, tickers


@lru_cache(maxsize=1)
def get_company_catalog() -> list[CompanyCatalogEntry]:
    if not RAW_SEC_ROOT.exists():
        return []

    entries: list[CompanyCatalogEntry] = []
    for ticker_dir in sorted(path for path in RAW_SEC_ROOT.iterdir() if path.is_dir()):
        company_name, tickers = load_submission_metadata(ticker_dir)
        primary_ticker = tickers[0]
        aliases = set()
        for ticker in tickers:
            aliases.add(normalize_alias(ticker))
        for variant in alias_variants(company_name):
            aliases.add(variant)
        entries.append(
            CompanyCatalogEntry(
                ticker=primary_ticker,
                name=company_name,
                aliases=tuple(sorted(alias for alias in aliases if alias)),
            )
        )
    return entries


def refresh_company_catalog() -> None:
    get_company_catalog.cache_clear()


def available_tickers() -> list[str]:
    return [entry.ticker for entry in get_company_catalog()]


def company_context_lines() -> list[str]:
    return [
        f"- {entry.ticker}: {entry.name}"
        for entry in get_company_catalog()
    ]


def company_name_for_ticker(ticker: str) -> str | None:
    normalized = ticker.upper()
    for entry in get_company_catalog():
        if entry.ticker == normalized:
            return entry.name
    return None


def alias_to_ticker_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for entry in get_company_catalog():
        mapping[normalize_alias(entry.ticker)] = entry.ticker
        for alias in entry.aliases:
            mapping[alias] = entry.ticker
    return mapping
