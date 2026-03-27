from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SearchResult:
    source: str
    score: float
    text: str
    metadata: dict


def lexical_search(question: str, documents: list[dict], top_k: int = 3) -> list[SearchResult]:
    query_terms = {term for term in question.lower().split() if len(term) > 2}
    scored_results: list[SearchResult] = []

    for document in documents:
        text = document["chunk_text"]
        tokens = set(text.lower().split())
        overlap = len(query_terms & tokens)
        if overlap == 0:
            continue
        scored_results.append(
            SearchResult(
                source=document["source"],
                score=float(overlap),
                text=text,
                metadata=document.get("metadata", {}),
            )
        )

    return sorted(scored_results, key=lambda item: item.score, reverse=True)[:top_k]
