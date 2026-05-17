from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from agent.company_catalog import extract_ticker_mentions
from agent.openai_client import get_openai_client
from app.config import get_settings

FINANCIAL_RESEARCH_TERMS = (
    "10-k",
    "10-q",
    "8-k",
    "annual report",
    "sec",
    "filing",
    "revenue",
    "margin",
    "capex",
    "r&d",
    "earnings",
    "cash flow",
    "operating income",
    "growth",
    "risk",
    "strategy",
    "management",
    "guidance",
    "forecast",
    "projection",
    "estimate",
    "next quarter",
    "public company",
    "stock",
    "shares",
    "financial",
    "finance",
    "ai narrative",
)
OUT_OF_SCOPE_TERMS = (
    "recipe",
    "cook",
    "poem",
    "song",
    "movie",
    "weather",
    "sports",
    "medical",
    "diagnose",
    "homework",
    "write code",
    "debug code",
    "travel",
    "restaurant",
)
REFUSAL_REASON = (
    "This assistant is limited to financial and filing research about US-listed public companies."
)


class ScopeDecision(BaseModel):
    in_scope: bool
    scope: Literal["us_public_company_financial_research", "out_of_scope", "ambiguous"]
    confidence: float
    reason: str
    detected_companies: list[str] = []
    used_llm: bool = False


class ScopeClassifierResult(BaseModel):
    in_scope: bool
    confidence: float
    reason: str
    detected_companies: list[str] = []


SCOPE_SYSTEM_PROMPT = """
You are a scope gate for a public-company research assistant.
Classify whether the user question is in scope.

In scope:
- financial, strategic, risk, management-commentary, SEC filing, or metric questions
- about US-listed public companies or plausible public-company tickers

Out of scope:
- cooking, travel, medical, entertainment, coding, homework, general advice, or anything unrelated to public-company financial/filing research

Return only the structured classification.
""".strip()


def decide_scope(question: str, detected_companies: list[str] | None = None) -> ScopeDecision:
    detected_companies = detected_companies or extract_ticker_mentions(question)
    deterministic = deterministic_scope_decision(question, detected_companies)
    if deterministic.scope != "ambiguous":
        return deterministic

    try:
        return llm_scope_decision(question, detected_companies)
    except Exception:
        return ScopeDecision(
            in_scope=False,
            scope="out_of_scope",
            confidence=0.5,
            reason=REFUSAL_REASON,
            detected_companies=detected_companies,
            used_llm=False,
        )


def deterministic_scope_decision(
    question: str, detected_companies: list[str] | None = None
) -> ScopeDecision:
    detected_companies = detected_companies or []
    normalized = f" {question.lower()} "
    has_financial_intent = any(term in normalized for term in FINANCIAL_RESEARCH_TERMS)
    has_out_of_scope_intent = any(term in normalized for term in OUT_OF_SCOPE_TERMS)

    if detected_companies and has_financial_intent:
        return ScopeDecision(
            in_scope=True,
            scope="us_public_company_financial_research",
            confidence=0.95,
            reason="Question mentions a detected public company and financial or filing research intent.",
            detected_companies=detected_companies,
        )

    if has_out_of_scope_intent and not has_financial_intent:
        return ScopeDecision(
            in_scope=False,
            scope="out_of_scope",
            confidence=0.95,
            reason=REFUSAL_REASON,
            detected_companies=detected_companies,
        )

    if has_financial_intent and not has_out_of_scope_intent:
        return ScopeDecision(
            in_scope=True,
            scope="us_public_company_financial_research",
            confidence=0.85,
            reason="Question contains financial or filing research intent.",
            detected_companies=detected_companies,
        )

    if detected_companies and not has_out_of_scope_intent:
        return ScopeDecision(
            in_scope=True,
            scope="us_public_company_financial_research",
            confidence=0.75,
            reason="Question mentions a detected public company and is not clearly out of scope.",
            detected_companies=detected_companies,
        )

    return ScopeDecision(
        in_scope=False,
        scope="ambiguous",
        confidence=0.4,
        reason="Question scope is ambiguous from deterministic rules.",
        detected_companies=detected_companies,
    )


def llm_scope_decision(question: str, detected_companies: list[str]) -> ScopeDecision:
    settings = get_settings()
    client = get_openai_client()
    response = client.responses.parse(
        model=settings.openai_model,
        reasoning={"effort": settings.openai_reasoning_effort},
        instructions=SCOPE_SYSTEM_PROMPT,
        input=(
            f"Question: {question}\n"
            f"Detected companies/tickers: {', '.join(detected_companies) or 'none'}"
        ),
        text_format=ScopeClassifierResult,
    )
    parsed = response.output_parsed
    return ScopeDecision(
        in_scope=parsed.in_scope,
        scope="us_public_company_financial_research" if parsed.in_scope else "out_of_scope",
        confidence=parsed.confidence,
        reason=parsed.reason if parsed.in_scope else REFUSAL_REASON,
        detected_companies=parsed.detected_companies or detected_companies,
        used_llm=True,
    )
