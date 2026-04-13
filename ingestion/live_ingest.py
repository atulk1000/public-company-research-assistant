from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from agent.company_catalog import refresh_company_catalog
from agent.company_resolver import ResolvedCompany
from app.config import get_settings
from ingestion.embed_chunks import embed_pending_chunks
from ingestion.load_filing_texts import ingest_company_documents
from ingestion.load_sec_data import CompanyRecord, ingest_company
from ingestion.raw_storage import company_directory


ProgressCallback = Callable[[str, str], None]


@dataclass
class LiveIngestResult:
    ticker: str
    company_name: str
    used_cache: bool
    structured_counts: dict[str, int]
    document_counts: dict[str, int]
    embedding_counts: dict[str, int]


def get_connection():
    settings = get_settings()
    return psycopg.connect(settings.database_url, row_factory=dict_row)


def report_progress(callback: ProgressCallback | None, step: str, message: str) -> None:
    if callback is not None:
        callback(step, message)


def upsert_company(conn: psycopg.Connection, resolved: ResolvedCompany) -> CompanyRecord:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO companies (cik, ticker, name)
            VALUES (%s, %s, %s)
            ON CONFLICT (ticker)
            DO UPDATE SET cik = EXCLUDED.cik, name = EXCLUDED.name
            RETURNING company_id, cik, ticker, name;
            """,
            (resolved.cik, resolved.ticker, resolved.company_name),
        )
        row = cursor.fetchone()
    return CompanyRecord(**row)


def latest_modified_time(path: Path) -> datetime | None:
    if not path.exists():
        return None

    candidates = [path]
    if path.is_dir():
        candidates = [item for item in path.rglob("*") if item.is_file()]
        if not candidates:
            return None

    modified = max(item.stat().st_mtime for item in candidates)
    return datetime.fromtimestamp(modified, tz=timezone.utc)


def cache_is_fresh(company: CompanyRecord, require_unstructured: bool) -> bool:
    settings = get_settings()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.live_cache_hours)
    company_dir = company_directory(company.ticker)
    submissions_mtime = latest_modified_time(company_dir / "submissions.json")
    facts_mtime = latest_modified_time(company_dir / "companyfacts.json")

    if submissions_mtime is None or facts_mtime is None or submissions_mtime < cutoff or facts_mtime < cutoff:
        return False

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS count FROM derived_metrics WHERE company_id = %s;", (company.company_id,))
            metric_count = cursor.fetchone()["count"]
            if metric_count == 0:
                return False

            if require_unstructured:
                cursor.execute("SELECT COUNT(*) AS count FROM documents WHERE company_id = %s;", (company.company_id,))
                document_count = cursor.fetchone()["count"]
                cursor.execute("SELECT COUNT(*) AS count FROM document_chunks WHERE company_id = %s AND embedding IS NOT NULL;", (company.company_id,))
                embedded_chunk_count = cursor.fetchone()["count"]
                filings_mtime = latest_modified_time(company_dir / "filings")
                if document_count == 0 or embedded_chunk_count == 0 or filings_mtime is None or filings_mtime < cutoff:
                    return False

    return True


def run_live_ingestion(
    resolved: ResolvedCompany,
    required_sources: list[str],
    progress_callback: ProgressCallback | None = None,
) -> LiveIngestResult:
    require_unstructured = "unstructured" in required_sources
    report_progress(progress_callback, "resolve", f"Resolved {resolved.company_name} ({resolved.ticker}).")

    with get_connection() as conn:
        company = upsert_company(conn, resolved)
        conn.commit()

    report_progress(progress_callback, "cache", "Checking local cache freshness...")
    if cache_is_fresh(company, require_unstructured=require_unstructured):
        refresh_company_catalog()
        return LiveIngestResult(
            ticker=company.ticker,
            company_name=company.name,
            used_cache=True,
            structured_counts={},
            document_counts={},
            embedding_counts={},
        )

    report_progress(progress_callback, "structured", "Fetching and loading structured SEC data...")
    with get_connection() as conn:
        refreshed_company = upsert_company(conn, resolved)
        structured_counts = ingest_company(conn, refreshed_company)
        conn.commit()

    document_counts = {"documents": 0, "chunks": 0}
    embedding_counts = {"updated_chunks": 0, "batches": 0}

    if require_unstructured:
        report_progress(progress_callback, "documents", "Fetching filing documents and parsing text...")
        with get_connection() as conn:
            refreshed_company = upsert_company(conn, resolved)
            document_counts = ingest_company_documents(
                conn,
                refreshed_company,
                filing_limit=get_settings().max_document_filings_per_company,
            )
            conn.commit()

        report_progress(progress_callback, "embeddings", "Generating embeddings for filing chunks...")
        updated_chunks, batches = embed_pending_chunks(company_id=refreshed_company.company_id)
        embedding_counts = {"updated_chunks": updated_chunks, "batches": batches}

    refresh_company_catalog()
    return LiveIngestResult(
        ticker=company.ticker,
        company_name=company.name,
        used_cache=False,
        structured_counts=structured_counts,
        document_counts=document_counts,
        embedding_counts=embedding_counts,
    )
