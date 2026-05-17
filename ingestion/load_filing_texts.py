from __future__ import annotations

import html
import os
import re
import sys
import time
import unicodedata
from html.parser import HTMLParser
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ingestion.chunk_documents import chunk_text
from ingestion.load_sec_data import (
    CompanyRecord,
    get_connection,
    load_settings,
    load_target_companies,
)
from ingestion.raw_storage import exhibit_html_path, filing_html_path, save_text
from ingestion.sec_api import sec_headers
from ingestion.sec_exhibits import fetch_filing_index, extract_high_value_exhibits
from ingestion.source_registry import (
    document_form_priority_case_sql,
    is_supported_event_exhibit_parent_form,
)

REQUEST_PAUSE_SECONDS = 0.25
DEFAULT_MAX_FILINGS_PER_COMPANY = 12
MOJIBAKE_REPLACEMENTS = {
    "â": "'",
    "â": "'",
    "â": '"',
    "â": '"',
    "â": "-",
    "â": "-",
    "â¢": "-",
    "â": "[x]",
    "â": "[ ]",
    "â ": "(1)",
    "â¡": "(2)",
    "â": "-",
}


class FilingHTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._ignore_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style", "noscript"}:
            self._ignore_depth += 1
        elif tag in {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4"}:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._ignore_depth > 0:
            self._ignore_depth -= 1
        elif tag in {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4"}:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._ignore_depth == 0 and data.strip():
            self._parts.append(data.strip())

    def get_text(self) -> str:
        text = "".join(self._parts)
        return clean_extracted_text(text)


def repair_mojibake(text: str) -> str:
    suspicious_markers = ("â", "Ã", "ð", "�")
    if not any(marker in text for marker in suspicious_markers):
        return text

    try:
        repaired = text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text

    # Prefer the repaired version when it reduces common mojibake markers.
    original_noise = sum(text.count(marker) for marker in suspicious_markers)
    repaired_noise = sum(repaired.count(marker) for marker in suspicious_markers)
    return repaired if repaired_noise < original_noise else text


def clean_extracted_text(text: str) -> str:
    cleaned = html.unescape(text)
    cleaned = cleaned.replace("\xa0", " ")
    cleaned = repair_mojibake(cleaned)
    for bad, good in MOJIBAKE_REPLACEMENTS.items():
        cleaned = cleaned.replace(bad, good)
    cleaned = unicodedata.normalize("NFKC", cleaned)

    lines = []
    for line in cleaned.splitlines():
        collapsed = " ".join(line.split())
        if collapsed:
            lines.append(collapsed)

    cleaned = "\n\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def max_filings_per_company() -> int:
    raw_value = os.getenv("MAX_DOCUMENT_FILINGS_PER_COMPANY", str(DEFAULT_MAX_FILINGS_PER_COMPANY))
    try:
        return max(1, int(raw_value))
    except ValueError:
        return DEFAULT_MAX_FILINGS_PER_COMPANY


def load_recent_filings(conn, company: CompanyRecord, limit: int) -> list[dict]:
    priority_case = document_form_priority_case_sql("form_type")
    with conn.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT filing_id, accession_no, form_type, filing_date::text AS filing_date, source_url
            FROM filings
            WHERE company_id = %s
              AND source_url IS NOT NULL
            ORDER BY
                {priority_case},
                filing_date DESC
            LIMIT %s;
            """,
            (company.company_id, limit),
        )
        return cursor.fetchall()


def fetch_filing_html(source_url: str) -> str:
    with httpx.Client(timeout=60.0, headers=sec_headers(), follow_redirects=True) as client:
        response = client.get(source_url)
        response.raise_for_status()
        return response.text


def html_to_text(html: str) -> str:
    parser = FilingHTMLTextExtractor()
    parser.feed(html)
    return parser.get_text()


def clear_company_documents(conn, company_id: int) -> None:
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


def insert_document(
    conn,
    company: CompanyRecord,
    filing: dict,
    raw_text: str,
    doc_type: str | None = None,
    title: str | None = None,
    source_url: str | None = None,
) -> int:
    final_doc_type = doc_type or filing["form_type"]
    final_source_url = source_url or filing["source_url"]
    final_title = title or f"{company.ticker} {final_doc_type} {filing['filing_date']}"
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO documents (
                company_id,
                filing_id,
                doc_type,
                title,
                doc_date,
                source_url,
                raw_text
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING document_id;
            """,
            (
                company.company_id,
                filing["filing_id"],
                final_doc_type,
                final_title,
                filing["filing_date"],
                final_source_url,
                raw_text,
            ),
        )
        return cursor.fetchone()["document_id"]


def insert_chunks(conn, document_id: int, company_id: int, chunks) -> int:
    inserted = 0
    with conn.cursor() as cursor:
        for chunk in chunks:
            cursor.execute(
                """
                INSERT INTO document_chunks (
                    document_id,
                    company_id,
                    chunk_index,
                    section_name,
                    chunk_text,
                    token_count,
                    embedding,
                    start_char,
                    end_char
                )
                VALUES (%s, %s, %s, %s, %s, %s, NULL, %s, %s);
                """,
                (
                    document_id,
                    company_id,
                    chunk.chunk_index,
                    chunk.section_name,
                    chunk.chunk_text,
                    len(chunk.chunk_text.split()),
                    chunk.start_char,
                    chunk.end_char,
                ),
            )
            inserted += 1
    return inserted


def ingest_document_text(
    conn,
    company: CompanyRecord,
    filing: dict,
    raw_text: str,
    doc_type: str | None = None,
    title: str | None = None,
    source_url: str | None = None,
) -> dict[str, int]:
    if len(raw_text) < 500:
        return {"documents": 0, "chunks": 0}

    document_id = insert_document(
        conn,
        company,
        filing,
        raw_text,
        doc_type=doc_type,
        title=title,
        source_url=source_url,
    )
    chunks = chunk_text(raw_text, chunk_size=1200, overlap=150)
    return {
        "documents": 1,
        "chunks": insert_chunks(conn, document_id, company.company_id, chunks),
    }


def ingest_filing_exhibits(conn, company: CompanyRecord, filing: dict) -> dict[str, int]:
    if not is_supported_event_exhibit_parent_form(filing["form_type"]):
        return {"documents": 0, "chunks": 0, "exhibits": 0}

    try:
        index_payload = fetch_filing_index(filing["source_url"])
        exhibits = extract_high_value_exhibits(index_payload, filing["source_url"])
    except Exception:
        return {"documents": 0, "chunks": 0, "exhibits": 0}

    document_count = 0
    chunk_count = 0
    exhibit_count = 0
    for exhibit in exhibits:
        try:
            html = fetch_filing_html(exhibit.source_url)
        except Exception:
            continue
        save_text(
            html,
            exhibit_html_path(
                company.ticker,
                filing["filing_date"],
                filing["form_type"],
                filing["accession_no"],
                exhibit.exhibit_type,
                exhibit.filename,
            ),
        )
        time.sleep(REQUEST_PAUSE_SECONDS)
        raw_text = html_to_text(html)
        counts = ingest_document_text(
            conn,
            company,
            filing,
            raw_text,
            doc_type=f"{filing['form_type']} {exhibit.exhibit_type}",
            title=(
                f"{company.ticker} {filing['form_type']} {exhibit.exhibit_type} "
                f"{filing['filing_date']}"
            ),
            source_url=exhibit.source_url,
        )
        if counts["documents"]:
            exhibit_count += 1
            document_count += counts["documents"]
            chunk_count += counts["chunks"]

    return {"documents": document_count, "chunks": chunk_count, "exhibits": exhibit_count}


def ingest_company_documents(conn, company: CompanyRecord, filing_limit: int) -> dict[str, int]:
    filings = load_recent_filings(conn, company, filing_limit)
    clear_company_documents(conn, company.company_id)

    document_count = 0
    chunk_count = 0
    exhibit_count = 0
    for filing in filings:
        html = fetch_filing_html(filing["source_url"])
        save_text(
            html,
            filing_html_path(
                company.ticker,
                filing["filing_date"],
                filing["form_type"],
                filing["accession_no"],
            ),
        )
        time.sleep(REQUEST_PAUSE_SECONDS)
        raw_text = html_to_text(html)
        counts = ingest_document_text(conn, company, filing, raw_text)
        document_count += counts["documents"]
        chunk_count += counts["chunks"]

        exhibit_counts = ingest_filing_exhibits(conn, company, filing)
        document_count += exhibit_counts["documents"]
        chunk_count += exhibit_counts["chunks"]
        exhibit_count += exhibit_counts["exhibits"]

    return {"documents": document_count, "chunks": chunk_count, "exhibits": exhibit_count}


def main() -> None:
    settings = load_settings()
    filing_limit = max_filings_per_company()
    with get_connection() as conn:
        companies = load_target_companies(conn, settings.ticker_list)
        if not companies:
            raise RuntimeError(
                "No target companies found. Apply db/seed.sql before running filing text ingestion."
            )

        print(f"Loading filing text for up to {filing_limit} recent filings per company...")
        for company in companies:
            counts = ingest_company_documents(conn, company, filing_limit)
            conn.commit()
            print(
                f"- {company.ticker}: documents={counts['documents']}, "
                f"chunks={counts['chunks']}"
            )


if __name__ == "__main__":
    main()
