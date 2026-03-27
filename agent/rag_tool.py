from __future__ import annotations

from retrieval.hybrid_search import hybrid_search
from retrieval.rerank import rerank_results


SAMPLE_DOCUMENTS = [
    {
        "source": "msft_10q_q2_2025",
        "chunk_text": "Microsoft highlighted durable cloud demand and noted AI infrastructure investment remained elevated across the quarter.",
        "embedding": [108.0, 1.0, 0.0],
        "metadata": {"ticker": "MSFT", "doc_type": "10-Q", "doc_date": "2025-12-31"},
    },
    {
        "source": "googl_10q_q2_2025",
        "chunk_text": "Alphabet emphasized AI product adoption, efficiency gains, and continued discipline around capital allocation.",
        "embedding": [104.0, 1.0, 0.0],
        "metadata": {"ticker": "GOOGL", "doc_type": "10-Q", "doc_date": "2025-12-31"},
    },
    {
        "source": "amzn_letter_2025",
        "chunk_text": "Amazon described strong demand for AI services and reiterated that infrastructure expansion would pressure near-term capital intensity.",
        "embedding": [121.0, 1.0, 0.0],
        "metadata": {"ticker": "AMZN", "doc_type": "shareholder-letter", "doc_date": "2025-12-31"},
    },
]


def retrieve_evidence(question: str) -> list[dict]:
    results = hybrid_search(question, SAMPLE_DOCUMENTS, top_k=3)
    reranked = rerank_results(results, preferred_sources={"msft_10q_q2_2025", "googl_10q_q2_2025"})
    return [
        {
            "source": result.source,
            "score": round(result.score, 3),
            "text": result.text,
            "metadata": result.metadata,
        }
        for result in reranked
    ]
