from __future__ import annotations

from dataclasses import dataclass
import os

import psycopg
from openai import OpenAI
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row


EMBEDDING_DIMENSIONS = 1536
DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/company_assistant"
DEFAULT_BATCH_SIZE = 64
MAX_EMBEDDING_CHARS = 6000


@dataclass
class EmbeddedChunk:
    chunk_text: str
    embedding: list[float]


def get_database_url() -> str:
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def get_openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required to generate real embeddings.")
    return OpenAI(api_key=api_key)


def get_embedding_model() -> str:
    return os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")


def get_connection():
    conn = psycopg.connect(get_database_url(), row_factory=dict_row)
    register_vector(conn)
    return conn


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    client = get_openai_client()
    prepared_inputs = [text[:MAX_EMBEDDING_CHARS] for text in texts]
    response = client.embeddings.create(
        model=get_embedding_model(),
        input=prepared_inputs,
        dimensions=EMBEDDING_DIMENSIONS,
        encoding_format="float",
    )
    return [item.embedding for item in response.data]


def embed_chunk_texts(chunk_texts: list[str]) -> list[EmbeddedChunk]:
    embeddings = embed_texts(chunk_texts)
    return [
        EmbeddedChunk(chunk_text=chunk_text, embedding=embedding)
        for chunk_text, embedding in zip(chunk_texts, embeddings, strict=True)
    ]


def pending_chunk_batch_size() -> int:
    raw_value = os.getenv("EMBEDDING_BATCH_SIZE", str(DEFAULT_BATCH_SIZE))
    try:
        return max(1, int(raw_value))
    except ValueError:
        return DEFAULT_BATCH_SIZE


def load_pending_chunks(conn, limit: int, company_id: int | None = None) -> list[dict]:
    with conn.cursor() as cursor:
        if company_id is None:
            cursor.execute(
                """
                SELECT chunk_id, chunk_text
                FROM document_chunks
                WHERE embedding IS NULL
                ORDER BY chunk_id
                LIMIT %s;
                """,
                (limit,),
            )
        else:
            cursor.execute(
                """
                SELECT chunk_id, chunk_text
                FROM document_chunks
                WHERE embedding IS NULL
                  AND company_id = %s
                ORDER BY chunk_id
                LIMIT %s;
                """,
                (company_id, limit),
            )
        return cursor.fetchall()


def update_embeddings(conn, batch: list[dict], embeddings: list[list[float]]) -> None:
    with conn.cursor() as cursor:
        cursor.executemany(
            """
            UPDATE document_chunks
            SET embedding = %s
            WHERE chunk_id = %s;
            """,
            [(embedding, row["chunk_id"]) for row, embedding in zip(batch, embeddings, strict=True)],
        )


def embed_pending_chunks(company_id: int | None = None) -> tuple[int, int]:
    batch_size = pending_chunk_batch_size()
    updated_chunks = 0
    batches = 0

    with get_connection() as conn:
        while True:
            batch = load_pending_chunks(conn, batch_size, company_id=company_id)
            if not batch:
                break

            embeddings = embed_texts([row["chunk_text"] for row in batch])
            update_embeddings(conn, batch, embeddings)
            conn.commit()

            updated_chunks += len(batch)
            batches += 1
            print(f"Embedded {updated_chunks} chunks across {batches} batch(es)...")

    return updated_chunks, batches


def main() -> None:
    updated_chunks, batches = embed_pending_chunks()
    print(f"Embedding refresh complete. Updated {updated_chunks} chunks in {batches} batch(es).")


if __name__ == "__main__":
    main()
