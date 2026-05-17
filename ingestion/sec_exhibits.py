from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx

from ingestion.sec_api import sec_headers
from ingestion.source_registry import is_supported_exhibit_type


@dataclass(frozen=True)
class FilingExhibit:
    exhibit_type: str
    filename: str
    description: str | None
    source_url: str


def filing_directory_url(source_url: str) -> str:
    return source_url.rsplit("/", 1)[0] + "/"


def filing_index_json_url(source_url: str) -> str:
    return urljoin(filing_directory_url(source_url), "index.json")


def fetch_filing_index(source_url: str) -> dict:
    with httpx.Client(timeout=30.0, headers=sec_headers(), follow_redirects=True) as client:
        response = client.get(filing_index_json_url(source_url))
        response.raise_for_status()
        return response.json()


def extract_high_value_exhibits(index_payload: dict, filing_source_url: str) -> list[FilingExhibit]:
    base_url = filing_directory_url(filing_source_url)
    items = index_payload.get("directory", {}).get("item", [])
    exhibits: list[FilingExhibit] = []

    for item in items:
        filename = str(item.get("name") or "").strip()
        exhibit_type = _infer_exhibit_type(item, filename)
        if not filename or not is_supported_exhibit_type(exhibit_type):
            continue
        exhibits.append(
            FilingExhibit(
                exhibit_type=exhibit_type,
                filename=filename,
                description=item.get("description"),
                source_url=urljoin(base_url, filename),
            )
        )

    return sorted(exhibits, key=lambda exhibit: (exhibit.exhibit_type, exhibit.filename))


def _infer_exhibit_type(item: dict, filename: str) -> str:
    explicit_type = str(item.get("type") or "").upper()
    if is_supported_exhibit_type(explicit_type):
        return explicit_type

    combined = " ".join(
        str(value or "")
        for value in [
            filename,
            item.get("description"),
            item.get("document"),
        ]
    ).lower()

    # SEC directory indexes often expose file MIME icons such as "text.gif" rather
    # than exhibit labels. Filenames commonly encode EX-99.1 as ex991, ex99-1,
    # ex_99_01, etc.
    match = re.search(r"ex[-_ ]?99(?:[-_. ]?0?([12]))?", combined)
    if not match:
        return explicit_type

    suffix = match.group(1)
    return f"EX-99.{suffix}" if suffix else "EX-99"
