from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from agent.company_catalog import company_context_lines
from agent.openai_client import get_openai_client
from app.config import get_settings
from app.prompts import ROUTER_SYSTEM_PROMPT, ROUTER_USER_TEMPLATE


@dataclass
class RouteDecision:
    route: str
    reasons: list[str]


class RouteSelection(BaseModel):
    route: Literal["sql", "rag", "hybrid"]
    rationale: str


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


def classify_question_fallback(question: str, error: Exception | None = None) -> RouteDecision:
    normalized = question.lower()
    sql_hits = sorted(term for term in SQL_TERMS if term in normalized)
    rag_hits = sorted(term for term in RAG_TERMS if term in normalized)

    reasons: list[str] = []
    if error is not None:
        reasons.append(f"router fallback after OpenAI error: {error}")

    if sql_hits and rag_hits:
        reasons.extend([f"sql terms: {', '.join(sql_hits)}", f"rag terms: {', '.join(rag_hits)}"])
        return RouteDecision(route="hybrid", reasons=reasons)
    if sql_hits:
        reasons.append(f"sql terms: {', '.join(sql_hits)}")
        return RouteDecision(route="sql", reasons=reasons)
    if rag_hits:
        reasons.append(f"rag terms: {', '.join(rag_hits)}")
        return RouteDecision(route="rag", reasons=reasons)

    reasons.append("defaulted to hybrid for ambiguous question")
    return RouteDecision(route="hybrid", reasons=reasons)


def classify_question(question: str) -> RouteDecision:
    try:
        settings = get_settings()
        client = get_openai_client()
        response = client.responses.parse(
            model=settings.openai_model,
            reasoning={"effort": settings.openai_reasoning_effort},
            instructions=ROUTER_SYSTEM_PROMPT,
            input=ROUTER_USER_TEMPLATE.format(
                question=question,
                companies="\n".join(company_context_lines()) or "- none loaded yet",
            ),
            text_format=RouteSelection,
        )
        selection = response.output_parsed
        return RouteDecision(route=selection.route, reasons=[selection.rationale, "router=llm"])
    except Exception as exc:
        return classify_question_fallback(question, error=exc)
