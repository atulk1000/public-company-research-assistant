from __future__ import annotations

from pathlib import Path
import os
import re
import sys

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.sql_tool import extract_requested_tickers
from ingestion.embed_chunks import embed_texts
from retrieval.lexical_search import SearchResult, lexical_search
from retrieval.rerank import rerank_results


DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/company_assistant"
LEXICAL_CANDIDATE_LIMIT = 250
VECTOR_CANDIDATE_LIMIT = 12
NARRATIVE_TERMS = ("narrative", "commentary", "management", "ai", "artificial intelligence", "copilot", "openai", "gemini")
HIGH_SIGNAL_TERMS = (
    "artificial intelligence",
    " ai ",
    "ai ",
    " ai",
    "copilot",
    "openai",
    "gemini",
    "generative ai",
    "cloud and ai",
    "ai infrastructure",
    "ai engineering",
)
HIGH_SIGNAL_PHRASES = (
    "we are focused on",
    "we continue to",
    "our strategy",
    "our long-term strategic partnership",
    "investments in cloud and ai",
    "making ai helpful",
)
LOW_SIGNAL_PHRASES = (
    "table of contents",
    "report of independent registered public accounting firm",
    "financial statements",
    "form 10-q",
    "form 10-k",
    "commission file number",
    "part i",
    "item 1.",
    "item 2.",
    "item 3.",
    "item 4.",
    "note 1",
    "note 2",
    "note 12",
    "note 13",
    "index\n\npage",
)


def get_connection():
    database_url = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    conn = psycopg.connect(database_url, row_factory=dict_row)
    register_vector(conn)
    return conn


def is_low_signal_chunk(text: str) -> bool:
    normalized = text.lower()
    xbrl_markers = ("us-gaap:", "xbrli:", "iso4217:", "dei:")
    marker_hits = sum(normalized.count(marker) for marker in xbrl_markers)
    if marker_hits >= 3:
        return True

    noisy_phrases = (
        "commission file number",
        "securities and exchange commission",
        "large accelerated filer",
        "transition report pursuant",
    )
    if any(phrase in normalized for phrase in noisy_phrases):
        return True

    if normalized.count("\n\n") < 2 and len(re.findall(r"\d", normalized)) > 120:
        return True

    return False


def build_search_query(question: str, scope_tickers: list[str]) -> str:
    normalized_question = question.lower()
    if any(term in normalized_question for term in NARRATIVE_TERMS):
        extras = " ai artificial intelligence narrative management commentary strategy investment cloud infrastructure copilot openai gemini"
    else:
        extras = ""

    scope = " ".join(scope_tickers)
    return f"{question} {scope}{extras}".strip()


def adjust_result_scores(results: list[SearchResult], question: str) -> list[SearchResult]:
    normalized_question = question.lower()
    narrative_mode = any(term in normalized_question for term in NARRATIVE_TERMS)

    for result in results:
        text = result.text.lower()

        if narrative_mode:
            for term in HIGH_SIGNAL_TERMS:
                if term in text:
                    result.score += 1.0
            for phrase in HIGH_SIGNAL_PHRASES:
                if phrase in text:
                    result.score += 0.75
            for phrase in LOW_SIGNAL_PHRASES:
                if phrase in text:
                    result.score -= 1.25

        if text.startswith("metrics"):
            result.score -= 0.5
        if text.startswith("table of contents") or text.startswith("index"):
            result.score -= 2.0
        if len(re.findall(r"\d", text)) > 180:
            result.score -= 1.5

    return sorted(results, key=lambda item: item.score, reverse=True)


def load_lexical_candidates(requested_tickers: list[str] | None = None, limit: int = LEXICAL_CANDIDATE_LIMIT) -> list[dict]:
    requested_tickers = requested_tickers or []
    with get_connection() as conn:
        with conn.cursor() as cursor:
            if requested_tickers:
                cursor.execute(
                    """
                    SELECT
                        dc.chunk_id,
                        dc.chunk_text,
                        d.title,
                        d.doc_type,
                        d.doc_date::text AS doc_date,
                        d.source_url,
                        c.ticker
                    FROM document_chunks dc
                    JOIN documents d ON d.document_id = dc.document_id
                    JOIN companies c ON c.company_id = d.company_id
                    WHERE c.ticker = ANY(%s)
                    ORDER BY d.doc_date DESC NULLS LAST, dc.chunk_index
                    LIMIT %s;
                    """,
                    (requested_tickers, limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT
                        dc.chunk_id,
                        dc.chunk_text,
                        d.title,
                        d.doc_type,
                        d.doc_date::text AS doc_date,
                        d.source_url,
                        c.ticker
                    FROM document_chunks dc
                    JOIN documents d ON d.document_id = dc.document_id
                    JOIN companies c ON c.company_id = d.company_id
                    ORDER BY d.doc_date DESC NULLS LAST, dc.chunk_index
                    LIMIT %s;
                    """,
                    (limit,),
                )
            rows = cursor.fetchall()

    return [
        {
            "source": f"{row['ticker']}_{row['doc_type']}_{row['chunk_id']}",
            "chunk_text": row["chunk_text"],
            "metadata": {
                "ticker": row["ticker"],
                "doc_type": row["doc_type"],
                "doc_date": row["doc_date"],
                "title": row["title"],
                "source_url": row["source_url"],
            },
        }
        for row in rows
    ]


def vector_search_db(query_embedding: list[float], requested_tickers: list[str] | None = None, limit: int = VECTOR_CANDIDATE_LIMIT) -> list[SearchResult]:
    requested_tickers = requested_tickers or []
    with get_connection() as conn:
        with conn.cursor() as cursor:
            if requested_tickers:
                cursor.execute(
                    """
                    SELECT
                        dc.chunk_id,
                        dc.chunk_text,
                        d.title,
                        d.doc_type,
                        d.doc_date::text AS doc_date,
                        d.source_url,
                        c.ticker,
                        1 - (dc.embedding <=> %s) AS score
                    FROM document_chunks dc
                    JOIN documents d ON d.document_id = dc.document_id
                    JOIN companies c ON c.company_id = d.company_id
                    WHERE c.ticker = ANY(%s)
                      AND dc.embedding IS NOT NULL
                    ORDER BY dc.embedding <=> %s
                    LIMIT %s;
                    """,
                    (query_embedding, requested_tickers, query_embedding, limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT
                        dc.chunk_id,
                        dc.chunk_text,
                        d.title,
                        d.doc_type,
                        d.doc_date::text AS doc_date,
                        d.source_url,
                        c.ticker,
                        1 - (dc.embedding <=> %s) AS score
                    FROM document_chunks dc
                    JOIN documents d ON d.document_id = dc.document_id
                    JOIN companies c ON c.company_id = d.company_id
                    WHERE dc.embedding IS NOT NULL
                    ORDER BY dc.embedding <=> %s
                    LIMIT %s;
                    """,
                    (query_embedding, query_embedding, limit),
                )
            rows = cursor.fetchall()

    return [
        SearchResult(
            source=f"{row['ticker']}_{row['doc_type']}_{row['chunk_id']}",
            score=float(row["score"]),
            text=row["chunk_text"],
            metadata={
                "ticker": row["ticker"],
                "doc_type": row["doc_type"],
                "doc_date": row["doc_date"],
                "title": row["title"],
                "source_url": row["source_url"],
            },
        )
        for row in rows
    ]


def search_scope(question: str, scope_tickers: list[str]) -> list[SearchResult]:
    search_query = build_search_query(question, scope_tickers)
    lexical_documents = load_lexical_candidates(scope_tickers)
    lexical_results = lexical_search(search_query, lexical_documents, top_k=VECTOR_CANDIDATE_LIMIT)

    try:
        query_embedding = embed_texts([search_query])[0]
        vector_results = vector_search_db(query_embedding, scope_tickers, limit=VECTOR_CANDIDATE_LIMIT)
    except Exception:
        vector_results = []

    combined: dict[tuple[str, str], SearchResult] = {}
    for result in lexical_results + vector_results:
        key = (result.source, result.text)
        if key in combined:
            combined[key].score += result.score
        else:
            combined[key] = result

    reranked = rerank_results(list(combined.values()))
    reranked = adjust_result_scores(reranked, question)
    return [result for result in reranked if not is_low_signal_chunk(result.text)]


def diversify_results(results: list[SearchResult], requested_tickers: list[str], top_k: int) -> list[SearchResult]:
    if not requested_tickers:
        return results[:top_k]

    selected: list[SearchResult] = []
    seen_sources: set[str] = set()

    per_ticker_target = max(1, top_k // len(requested_tickers))
    for ticker in requested_tickers:
        ticker_results = [result for result in results if result.metadata.get("ticker") == ticker]
        for result in ticker_results[:per_ticker_target]:
            if result.source in seen_sources:
                continue
            selected.append(result)
            seen_sources.add(result.source)

    for result in results:
        if len(selected) >= top_k:
            break
        if result.source in seen_sources:
            continue
        selected.append(result)
        seen_sources.add(result.source)

    return selected[:top_k]


def retrieve_evidence(question: str, top_k: int = 6, requested_tickers: list[str] | None = None) -> list[dict]:
    requested_tickers = requested_tickers or extract_requested_tickers(question)
    if requested_tickers:
        combined_results: list[SearchResult] = []
        for ticker in requested_tickers:
            combined_results.extend(search_scope(question, [ticker])[: max(2, top_k // len(requested_tickers))])

        if len(combined_results) < top_k:
            combined_results.extend(search_scope(question, requested_tickers))
        results = rerank_results(combined_results)
    else:
        results = search_scope(question, requested_tickers)
    diversified = diversify_results(results, requested_tickers, top_k=top_k)
    return [
        {
            "source": result.source,
            "score": round(result.score, 3),
            "text": result.text,
            "metadata": result.metadata,
        }
        for result in diversified
    ]
