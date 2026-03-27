from __future__ import annotations

from retrieval.lexical_search import SearchResult


def rerank_results(results: list[SearchResult], preferred_sources: set[str] | None = None) -> list[SearchResult]:
    preferred_sources = preferred_sources or set()
    for result in results:
        if result.source in preferred_sources:
            result.score += 0.25
    return sorted(results, key=lambda item: item.score, reverse=True)
