from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import psycopg

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ingestion.embed_chunks import embed_pending_chunks
from ingestion.fetch_company_facts import extract_usd_facts
from ingestion.fetch_sec_filings import extract_recent_filings
from ingestion.freshness import upsert_company_freshness, utc_now
from ingestion.load_filing_texts import html_to_text, insert_chunks, insert_document
from ingestion.load_sec_data import (
    CompanyRecord,
    TARGET_CONCEPTS,
    build_metric_rows,
    clear_company_data,
    dedupe_facts,
    get_connection,
    replace_derived_metrics,
    replace_facts,
    replace_filings,
)
from ingestion.raw_storage import RAW_SEC_ROOT


def target_tickers() -> list[str]:
    raw_value = os.getenv("TARGET_TICKERS", "").strip()
    if raw_value:
        return [ticker.strip().upper() for ticker in raw_value.split(",") if ticker.strip()]
    return sorted(path.name.upper() for path in RAW_SEC_ROOT.iterdir() if path.is_dir())


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def company_from_raw(conn: psycopg.Connection, ticker: str, submissions: dict, company_facts: dict) -> CompanyRecord:
    cik_value = company_facts.get("cik") or submissions.get("cik")
    name = company_facts.get("entityName") or submissions.get("name") or ticker
    if cik_value is None:
        raise RuntimeError(f"Missing CIK in raw data for {ticker}.")

    cik = str(cik_value).zfill(10)
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO companies (cik, ticker, name)
            VALUES (%s, %s, %s)
            ON CONFLICT (ticker)
            DO UPDATE SET cik = EXCLUDED.cik, name = EXCLUDED.name
            RETURNING company_id, cik, ticker, name;
            """,
            (cik, ticker, name),
        )
        row = cursor.fetchone()
    return CompanyRecord(**row)


def filing_rows_by_accession(conn: psycopg.Connection, company_id: int, limit: int) -> list[dict]:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT filing_id, accession_no, form_type, filing_date::text AS filing_date, source_url
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
            (company_id, limit),
        )
        return cursor.fetchall()


def ingest_local_documents(conn: psycopg.Connection, company: CompanyRecord, filing_limit: int) -> dict[str, int]:
    filing_rows = filing_rows_by_accession(conn, company.company_id, filing_limit)
    filings_by_accession = {row["accession_no"]: row for row in filing_rows}

    document_count = 0
    chunk_count = 0
    filing_root = RAW_SEC_ROOT / company.ticker / "filings"
    if not filing_root.exists():
        return {"documents": 0, "chunks": 0}

    for html_path in sorted(filing_root.glob("*.html"), reverse=True):
        stem = html_path.stem
        try:
            date_and_form, accession_no = stem.rsplit("_", 1)
            filing_date, _ = date_and_form.split("_", 1)
        except ValueError:
            continue

        filing = filings_by_accession.get(accession_no)
        if filing is None:
            continue

        html_content = html_path.read_text(encoding="utf-8", errors="ignore")
        raw_text = html_to_text(html_content)
        if len(raw_text) < 500:
            continue

        document_id = insert_document(conn, company, filing, raw_text)
        from ingestion.chunk_documents import chunk_text

        chunks = chunk_text(raw_text, chunk_size=1200, overlap=150)
        chunk_count += insert_chunks(conn, document_id, company.company_id, chunks)
        document_count += 1

    return {"documents": document_count, "chunks": chunk_count}


def bootstrap_company(conn: psycopg.Connection, ticker: str, filing_limit: int, refresh_time) -> dict[str, int]:
    company_root = RAW_SEC_ROOT / ticker
    submissions_file = company_root / "submissions.json"
    company_facts_file = company_root / "companyfacts.json"
    if not submissions_file.exists() or not company_facts_file.exists():
        raise RuntimeError(f"Raw SEC files not found for {ticker}.")

    submissions = read_json(submissions_file)
    company_facts = read_json(company_facts_file)
    company = company_from_raw(conn, ticker, submissions, company_facts)

    recent_filings = extract_recent_filings(submissions)
    fact_rows = dedupe_facts(extract_usd_facts(company_facts, TARGET_CONCEPTS))

    clear_company_data(conn, company.company_id)
    filing_ids = replace_filings(conn, company, recent_filings)
    replace_facts(conn, company, filing_ids, fact_rows)
    metric_rows = build_metric_rows(company, fact_rows)
    replace_derived_metrics(conn, company, metric_rows)
    upsert_company_freshness(conn, company.company_id, structured_refreshed=True, refreshed_at=refresh_time)

    document_counts = ingest_local_documents(conn, company, filing_limit)
    upsert_company_freshness(conn, company.company_id, documents_refreshed=True, refreshed_at=refresh_time)

    return {
        "company_id": company.company_id,
        "filings": len(recent_filings),
        "facts": len(fact_rows),
        "metric_rows": len(metric_rows),
        "documents": document_counts["documents"],
        "chunks": document_counts["chunks"],
    }


def document_filing_limit() -> int:
    raw_value = os.getenv("MAX_DOCUMENT_FILINGS_PER_COMPANY", "12")
    try:
        return max(1, int(raw_value))
    except ValueError:
        return 12


def main() -> None:
    tickers = target_tickers()
    if not tickers:
        raise RuntimeError("No raw SEC directories were found under data/raw/sec.")

    refresh_time = utc_now()
    results: dict[str, dict[str, int]] = {}
    filing_limit = document_filing_limit()
    company_ids: list[int] = []

    with get_connection() as conn:
        for ticker in tickers:
            print(f"Bootstrapping {ticker} from local raw SEC files...")
            results[ticker] = bootstrap_company(conn, ticker, filing_limit, refresh_time)
            company_ids.append(results[ticker]["company_id"])
            conn.commit()

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if api_key:
        updated_chunks, batches = embed_pending_chunks()
        with get_connection() as conn:
            for company_id in company_ids:
                upsert_company_freshness(conn, company_id, embeddings_refreshed=True, refreshed_at=refresh_time)
            conn.commit()
        print(f"Generated embeddings for {updated_chunks} chunks across {batches} batch(es).")
    else:
        print("OPENAI_API_KEY not set. Skipping embedding bootstrap; SQL-only demo paths will still work.")

    print("Local raw bootstrap complete.")
    for ticker, counts in results.items():
        print(
            f"- {ticker}: filings={counts['filings']}, facts={counts['facts']}, "
            f"metrics={counts['metric_rows']}, documents={counts['documents']}, chunks={counts['chunks']}"
        )


if __name__ == "__main__":
    main()
