from __future__ import annotations

from typing import Literal
import re

from pydantic import BaseModel, Field

from agent.company_catalog import company_context_lines
from agent.openai_client import get_openai_client
from agent.router import classify_question_fallback
from app.config import get_settings
from app.prompts import PLANNER_SYSTEM_PROMPT, PLANNER_USER_TEMPLATE


class QuestionPlan(BaseModel):
    company_name: str | None = None
    ticker: str | None = None
    route: Literal["sql", "rag", "hybrid"]
    required_sources: list[Literal["structured", "unstructured"]] = Field(default_factory=list)
    reasoning: str


def planner_fallback(question: str, clarification: str | None = None, error: Exception | None = None) -> QuestionPlan:
    route_decision = classify_question_fallback(question, error=error)
    combined_text = " ".join(part for part in [question, clarification or ""] if part).strip()
    ticker_match = re.search(r"\b[A-Z]{1,5}\b", combined_text)
    ticker = ticker_match.group(0).upper() if ticker_match else None

    company_name = clarification.strip() if clarification else None
    required_sources: list[Literal["structured", "unstructured"]] = []
    if route_decision.route in {"sql", "hybrid"}:
        required_sources.append("structured")
    if route_decision.route in {"rag", "hybrid"}:
        required_sources.append("unstructured")

    reasoning = "; ".join(route_decision.reasons)
    if ticker and not company_name:
        company_name = ticker

    return QuestionPlan(
        company_name=company_name,
        ticker=ticker,
        route=route_decision.route,  # type: ignore[arg-type]
        required_sources=required_sources,
        reasoning=reasoning or "fallback planner output",
    )


def plan_question(question: str, clarification: str | None = None) -> QuestionPlan:
    try:
        settings = get_settings()
        client = get_openai_client()
        response = client.responses.parse(
            model=settings.openai_model,
            reasoning={"effort": settings.openai_reasoning_effort},
            instructions=PLANNER_SYSTEM_PROMPT,
            input=PLANNER_USER_TEMPLATE.format(
                question=question,
                clarification=clarification or "None",
                companies="\n".join(company_context_lines()) or "- none loaded yet",
            ),
            text_format=QuestionPlan,
        )
        plan = response.output_parsed
        if not plan.required_sources:
            plan.required_sources = ["structured"] if plan.route == "sql" else ["unstructured"] if plan.route == "rag" else ["structured", "unstructured"]
        return plan
    except Exception as exc:
        return planner_fallback(question, clarification=clarification, error=exc)
