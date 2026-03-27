from __future__ import annotations

from math import sqrt

from retrieval.lexical_search import SearchResult


def _dot(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=False))


def _norm(vector: list[float]) -> float:
    return sqrt(sum(value * value for value in vector)) or 1.0


def cosine_similarity(left: list[float], right: list[float]) -> float:
    return _dot(left, right) / (_norm(left) * _norm(right))


def vector_search(query_embedding: list[float], documents: list[dict], top_k: int = 3) -> list[SearchResult]:
    results: list[SearchResult] = []
    for document in documents:
        score = cosine_similarity(query_embedding, document["embedding"])
        results.append(
            SearchResult(
                source=document["source"],
                score=score,
                text=document["chunk_text"],
                metadata=document.get("metadata", {}),
            )
        )
    return sorted(results, key=lambda item: item.score, reverse=True)[:top_k]
