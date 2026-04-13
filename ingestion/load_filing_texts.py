from __future__ import annotations

import html
from html.parser import HTMLParser
import os
from pathlib import Path
import re
import sys
import time
import unicodedata

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ingestion.chunk_documents import chunk_text
from ingestion.load_sec_data import CompanyRecord, get_connection, load_settings, load_target_companies
from ingestion.raw_storage import filing_html_path, save_text
from ingestion.sec_api import sec_headers


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
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT filing_id, form_type, filing_date::text AS filing_date, source_url
            FROM filings
            WHERE company_id = %s
              AND source_url IS NOT NULL
            ORDER BY
                CASE
                    WHEN form_type IN ('10-Q', '10-Q/A', '10-K', '10-K/A', '20-F', '20-F/A', '40-F', '40-F/A') THEN 1
                    WHEN form_type IN ('6-K', '6-K/A', '8-K', '8-K/A') THEN 2
                    WHEN form_type IN ('DEF 14A', 'DEFA14A') THEN 3
                    ELSE 4
                END,
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


def insert_document(conn, company: CompanyRecord, filing: dict, raw_text: str) -> int:
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
                filing["form_type"],
                f"{company.ticker} {filing['form_type']} {filing['filing_date']}",
                filing["filing_date"],
                filing["source_url"],
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


def ingest_company_documents(conn, company: CompanyRecord, filing_limit: int) -> dict[str, int]:
    filings = load_recent_filings(conn, company, filing_limit)
    clear_company_documents(conn, company.company_id)

    document_count = 0
    chunk_count = 0
    for filing in filings:
        html = fetch_filing_html(filing["source_url"])
        accession_no = filing["source_url"].rstrip("/").split("/")[-2]
        save_text(
            html,
            filing_html_path(
                company.ticker,
                filing["filing_date"],
                filing["form_type"],
                accession_no,
            ),
        )
        time.sleep(REQUEST_PAUSE_SECONDS)
        raw_text = html_to_text(html)
        if len(raw_text) < 500:
            continue

        document_id = insert_document(conn, company, filing, raw_text)
        chunks = chunk_text(raw_text, chunk_size=1200, overlap=150)
        chunk_count += insert_chunks(conn, document_id, company.company_id, chunks)
        document_count += 1

    return {"documents": document_count, "chunks": chunk_count}


def main() -> None:
    settings = load_settings()
    filing_limit = max_filings_per_company()
    with get_connection() as conn:
        companies = load_target_companies(conn, settings.ticker_list)
        if not companies:
            raise RuntimeError("No target companies found. Apply db/seed.sql before running filing text ingestion.")

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
