from __future__ import annotations

from datetime import datetime, timedelta, timezone

import psycopg
from psycopg.rows import dict_row


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def get_company_freshness(conn: psycopg.Connection, company_id: int) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT
                company_id,
                structured_last_refreshed_at,
                documents_last_refreshed_at,
                embeddings_last_refreshed_at,
                updated_at
            FROM company_data_freshness
            WHERE company_id = %s;
            """,
            (company_id,),
        )
        return cursor.fetchone()


def upsert_company_freshness(
    conn: psycopg.Connection,
    company_id: int,
    *,
    structured_refreshed: bool = False,
    documents_refreshed: bool = False,
    embeddings_refreshed: bool = False,
    refreshed_at: datetime | None = None,
) -> dict:
    refreshed_at = refreshed_at or utc_now()

    with conn.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            INSERT INTO company_data_freshness (
                company_id,
                structured_last_refreshed_at,
                documents_last_refreshed_at,
                embeddings_last_refreshed_at,
                updated_at
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s
            )
            ON CONFLICT (company_id)
            DO UPDATE SET
                structured_last_refreshed_at = CASE
                    WHEN EXCLUDED.structured_last_refreshed_at IS NOT NULL THEN EXCLUDED.structured_last_refreshed_at
                    ELSE company_data_freshness.structured_last_refreshed_at
                END,
                documents_last_refreshed_at = CASE
                    WHEN EXCLUDED.documents_last_refreshed_at IS NOT NULL THEN EXCLUDED.documents_last_refreshed_at
                    ELSE company_data_freshness.documents_last_refreshed_at
                END,
                embeddings_last_refreshed_at = CASE
                    WHEN EXCLUDED.embeddings_last_refreshed_at IS NOT NULL THEN EXCLUDED.embeddings_last_refreshed_at
                    ELSE company_data_freshness.embeddings_last_refreshed_at
                END,
                updated_at = EXCLUDED.updated_at
            RETURNING
                company_id,
                structured_last_refreshed_at,
                documents_last_refreshed_at,
                embeddings_last_refreshed_at,
                updated_at;
            """,
            (
                company_id,
                refreshed_at if structured_refreshed else None,
                refreshed_at if documents_refreshed else None,
                refreshed_at if embeddings_refreshed else None,
                refreshed_at,
            ),
        )
        return cursor.fetchone()


def company_data_is_fresh(
    conn: psycopg.Connection,
    company_id: int,
    *,
    max_age_hours: int,
    require_unstructured: bool,
) -> bool:
    freshness = get_company_freshness(conn, company_id)
    if not freshness:
        return False

    cutoff = utc_now() - timedelta(hours=max_age_hours)
    structured_refreshed_at = freshness.get("structured_last_refreshed_at")
    if structured_refreshed_at is None or structured_refreshed_at < cutoff:
        return False

    with conn.cursor(row_factory=dict_row) as cursor:
        cursor.execute("SELECT COUNT(*) AS count FROM derived_metrics WHERE company_id = %s;", (company_id,))
        metric_count = cursor.fetchone()["count"]
        if metric_count == 0:
            return False

        if require_unstructured:
            documents_refreshed_at = freshness.get("documents_last_refreshed_at")
            embeddings_refreshed_at = freshness.get("embeddings_last_refreshed_at")
            if documents_refreshed_at is None or embeddings_refreshed_at is None:
                return False
            if documents_refreshed_at < cutoff or embeddings_refreshed_at < cutoff:
                return False

            cursor.execute("SELECT COUNT(*) AS count FROM documents WHERE company_id = %s;", (company_id,))
            document_count = cursor.fetchone()["count"]
            cursor.execute(
                "SELECT COUNT(*) AS count FROM document_chunks WHERE company_id = %s AND embedding IS NOT NULL;",
                (company_id,),
            )
            embedded_chunk_count = cursor.fetchone()["count"]
            if document_count == 0 or embedded_chunk_count == 0:
                return False

    return True


def serialize_freshness(freshness: dict | None) -> dict | None:
    if not freshness:
        return None

    serialized: dict[str, str | int | None] = {"company_id": freshness.get("company_id")}
    for key in (
        "structured_last_refreshed_at",
        "documents_last_refreshed_at",
        "embeddings_last_refreshed_at",
        "updated_at",
    ):
        value = freshness.get(key)
        serialized[key] = value.isoformat() if hasattr(value, "isoformat") and value is not None else value
    return serialized
