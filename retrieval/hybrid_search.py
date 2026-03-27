from __future__ import annotations

from ingestion.embed_chunks import fake_embed
from retrieval.lexical_search import SearchResult, lexical_search
from retrieval.vector_search import vector_search


def hybrid_search(question: str, documents: list[dict], top_k: int = 3) -> list[SearchResult]:
    lexical_results = lexical_search(question, documents, top_k=top_k * 2)
    vector_results = vector_search(fake_embed(question), documents, top_k=top_k * 2)

    combined: dict[tuple[str, str], SearchResult] = {}
    for result in lexical_results + vector_results:
        key = (result.source, result.text)
        if key not in combined:
            combined[key] = result
        else:
            combined[key].score += result.score

    return sorted(combined.values(), key=lambda item: item.score, reverse=True)[:top_k]
