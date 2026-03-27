from __future__ import annotations

from dataclasses import dataclass


SQL_TERMS = {
    "compare",
    "trend",
    "growth",
    "margin",
    "capex",
    "revenue",
    "quarter",
    "highest",
    "lowest",
    "increase",
}

RAG_TERMS = {
    "commentary",
    "tone",
    "management",
    "guidance",
    "narrative",
    "said",
    "mentions",
    "theme",
    "themes",
    "risk",
}


@dataclass
class RouteDecision:
    route: str
    reasons: list[str]


def classify_question(question: str) -> RouteDecision:
    normalized = question.lower()
    sql_hits = sorted(term for term in SQL_TERMS if term in normalized)
    rag_hits = sorted(term for term in RAG_TERMS if term in normalized)

    if sql_hits and rag_hits:
        return RouteDecision(route="hybrid", reasons=[f"sql terms: {', '.join(sql_hits)}", f"rag terms: {', '.join(rag_hits)}"])
    if sql_hits:
        return RouteDecision(route="sql", reasons=[f"sql terms: {', '.join(sql_hits)}"])
    if rag_hits:
        return RouteDecision(route="rag", reasons=[f"rag terms: {', '.join(rag_hits)}"])
    return RouteDecision(route="hybrid", reasons=["defaulted to hybrid for ambiguous question"])
