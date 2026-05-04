from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import psycopg
from psycopg.rows import dict_row

from agent.company_catalog import refresh_company_catalog
from agent.company_resolver import ResolvedCompany
from app.config import get_settings
from ingestion.embed_chunks import embed_pending_chunks
from ingestion.freshness import (
    company_data_is_fresh,
    get_company_freshness,
    serialize_freshness,
    upsert_company_freshness,
)
from ingestion.load_filing_texts import ingest_company_documents
from ingestion.load_sec_data import CompanyRecord, ingest_company


ProgressCallback = Callable[[str, str], None]


@dataclass
class LiveIngestResult:
    ticker: str
    company_name: str
    used_cache: bool
    structured_counts: dict[str, int]
    document_counts: dict[str, int]
    embedding_counts: dict[str, int]
    freshness: dict | None


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


def cache_is_fresh(company: CompanyRecord, require_unstructured: bool) -> bool:
    settings = get_settings()
    with get_connection() as conn:
        return company_data_is_fresh(
            conn,
            company.company_id,
            max_age_hours=settings.live_cache_hours,
            require_unstructured=require_unstructured,
        )


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
        with get_connection() as conn:
            freshness = serialize_freshness(get_company_freshness(conn, company.company_id))
        refresh_company_catalog()
        return LiveIngestResult(
            ticker=company.ticker,
            company_name=company.name,
            used_cache=True,
            structured_counts={},
            document_counts={},
            embedding_counts={},
            freshness=freshness,
        )

    report_progress(progress_callback, "structured", "Fetching and loading structured SEC data...")
    with get_connection() as conn:
        refreshed_company = upsert_company(conn, resolved)
        structured_counts = ingest_company(conn, refreshed_company)
        freshness_row = upsert_company_freshness(conn, refreshed_company.company_id, structured_refreshed=True)
        conn.commit()

    document_counts = {"documents": 0, "chunks": 0}
    embedding_counts = {"updated_chunks": 0, "batches": 0}
    latest_freshness = freshness_row

    if require_unstructured:
        report_progress(progress_callback, "documents", "Fetching filing documents and parsing text...")
        with get_connection() as conn:
            refreshed_company = upsert_company(conn, resolved)
            document_counts = ingest_company_documents(
                conn,
                refreshed_company,
                filing_limit=get_settings().max_document_filings_per_company,
            )
            latest_freshness = upsert_company_freshness(conn, refreshed_company.company_id, documents_refreshed=True)
            conn.commit()

        report_progress(progress_callback, "embeddings", "Generating embeddings for filing chunks...")
        updated_chunks, batches = embed_pending_chunks(company_id=refreshed_company.company_id)
        embedding_counts = {"updated_chunks": updated_chunks, "batches": batches}
        with get_connection() as conn:
            latest_freshness = upsert_company_freshness(conn, refreshed_company.company_id, embeddings_refreshed=True)
            conn.commit()

    refresh_company_catalog()
    return LiveIngestResult(
        ticker=company.ticker,
        company_name=company.name,
        used_cache=False,
        structured_counts=structured_counts,
        document_counts=document_counts,
        embedding_counts=embedding_counts,
        freshness=serialize_freshness(latest_freshness),
    )
