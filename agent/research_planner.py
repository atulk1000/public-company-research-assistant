from __future__ import annotations

import re

from agent.research_plan import EvidenceRequirements, ResearchPlan, RouteName, SourceName, TierName
from agent.scope import REFUSAL_REASON, ScopeDecision, decide_scope
from agent.tier_decider import TierDecision, decide_tier

METRIC_KEYWORDS = {
    "capex_pct_revenue": ("capex", "capital expenditure", "capital intensity"),
    "rd_pct_revenue": ("r&d", "rd ", "research and development", "research"),
    "revenue_growth_yoy": ("growth", "revenue growth"),
    "revenue": ("revenue", "sales"),
    "gross_margin": ("gross margin",),
    "operating_margin": ("operating margin", "margin"),
}

DOCUMENT_THEMES = {
    "AI infrastructure": ("ai infrastructure", "infrastructure", "data center", "datacenter"),
    "Copilot": ("copilot",),
    "Azure AI": ("azure ai", "azure"),
    "OpenAI": ("openai",),
    "Gemini": ("gemini",),
    "Google Cloud AI": ("google cloud", "cloud ai"),
    "AI investment": ("ai investment", "artificial intelligence", "ai ", "generative ai"),
    "management commentary": ("management", "commentary", "said", "discuss"),
    "risk factors": ("risk", "risks"),
    "demand drivers": ("demand", "driver", "drivers"),
}

COMPARISON_TERMS = ("compare", "versus", " vs ", "against", "relative to")


def create_research_plan(
    question: str,
    decision: TierDecision | None = None,
    scope_decision: ScopeDecision | None = None,
) -> ResearchPlan:
    if scope_decision is None:
        scope_decision = decide_scope(question)
    if not scope_decision.in_scope:
        return _out_of_scope_plan(question, scope_decision)

    decision = decision or decide_tier(question)
    normalized = f" {question.lower()} "
    comparison = len(decision.companies) > 1 or any(term in normalized for term in COMPARISON_TERMS)
    required_sources = _required_sources(decision.route)
    required_metrics = _required_metrics(normalized, decision.route)
    document_themes = _document_themes(normalized, decision.route)
    time_window = _time_window(normalized)
    minimum_quarters = 4 if time_window == "last_four_quarters" else None

    evidence_requirements = EvidenceRequirements(
        sql_companies=decision.companies if "structured" in required_sources else [],
        rag_companies=decision.companies if "unstructured" in required_sources else [],
        minimum_quarters_per_company=minimum_quarters,
    )

    return ResearchPlan(
        question=question,
        in_scope=True,
        refusal_reason=None,
        companies=decision.companies,
        comparison=comparison,
        time_window=time_window,
        required_metrics=required_metrics,
        document_themes=document_themes,
        required_sources=required_sources,
        evidence_requirements=evidence_requirements,
        validation_checks=_validation_checks(required_sources, comparison, minimum_quarters),
        planned_steps=_planned_steps(required_sources, comparison, minimum_quarters),
        route_hint=_route_from_sources(required_sources),
        tier_hint=_tier_from_plan(decision, comparison, required_sources, document_themes),
        rationale=decision.rationale or "research plan derived from question intent",
    )


def _out_of_scope_plan(question: str, scope_decision: ScopeDecision) -> ResearchPlan:
    return ResearchPlan(
        question=question,
        in_scope=False,
        refusal_reason=scope_decision.reason or REFUSAL_REASON,
        companies=scope_decision.detected_companies,
        comparison=False,
        time_window=None,
        required_metrics=[],
        document_themes=[],
        required_sources=[],
        evidence_requirements=EvidenceRequirements(),
        validation_checks=["question is within app scope"],
        planned_steps=["refuse out-of-scope question before tool use"],
        route_hint="hybrid",
        tier_hint="hybrid_fast",
        rationale=scope_decision.reason or REFUSAL_REASON,
    )


def plan_context_question(plan: ResearchPlan, ticker: str | None = None) -> str:
    parts = [plan.question]
    if ticker:
        parts.append(f"Company focus: {ticker}.")
    if plan.time_window:
        parts.append(f"Time window: {plan.time_window}.")
    if plan.required_metrics:
        parts.append("Required metrics: " + ", ".join(plan.required_metrics) + ".")
    if plan.document_themes:
        parts.append("Document themes: " + ", ".join(plan.document_themes) + ".")
    return " ".join(parts)


def _required_sources(route: str) -> list[SourceName]:
    if route == "sql":
        return ["structured"]
    if route == "rag":
        return ["unstructured"]
    return ["structured", "unstructured"]


def _required_metrics(normalized_question: str, route: str) -> list[str]:
    if route == "rag":
        return []
    metrics = [
        metric
        for metric, keywords in METRIC_KEYWORDS.items()
        if any(keyword in normalized_question for keyword in keywords)
    ]
    if " ai " in normalized_question or "artificial intelligence" in normalized_question:
        metrics.extend(["rd_pct_revenue", "revenue_growth_yoy"])
    if not metrics and route in {"sql", "hybrid"}:
        metrics.append("revenue")
    return _dedupe(metrics)


def _document_themes(normalized_question: str, route: str) -> list[str]:
    if route == "sql":
        return []
    themes = [
        theme
        for theme, keywords in DOCUMENT_THEMES.items()
        if any(keyword in normalized_question for keyword in keywords)
    ]
    if " ai " in normalized_question or "artificial intelligence" in normalized_question:
        themes.append("AI investment")
    if not themes and route in {"rag", "hybrid"}:
        themes.append("management commentary")
    return _dedupe(themes)


def _time_window(normalized_question: str) -> str | None:
    if re.search(r"last\s+four\s+quarters|last\s+4\s+quarters", normalized_question):
        return "last_four_quarters"
    if "latest quarter" in normalized_question or "most recent quarter" in normalized_question:
        return "latest_quarter"
    if re.search(r"last\s+two\s+years|last\s+2\s+years", normalized_question):
        return "last_two_years"
    return None


def _validation_checks(
    required_sources: list[SourceName], comparison: bool, minimum_quarters: int | None
) -> list[str]:
    checks = []
    if "structured" in required_sources:
        checks.append("required companies have SQL rows")
        checks.append("required metrics are present or caveated")
    if "unstructured" in required_sources:
        checks.append("required companies have document evidence")
        checks.append("document evidence has citation metadata")
    if comparison:
        checks.append("comparison companies have balanced evidence coverage")
    if minimum_quarters:
        checks.append(f"at least {minimum_quarters} quarters per company are present or caveated")
    return checks


def _planned_steps(
    required_sources: list[SourceName], comparison: bool, minimum_quarters: int | None
) -> list[str]:
    steps = ["resolve companies"]
    if "structured" in required_sources:
        metric_step = "query required metrics"
        if minimum_quarters:
            metric_step += f" over last {minimum_quarters} quarters"
        steps.append(metric_step)
    if "unstructured" in required_sources:
        retrieval_step = "retrieve document evidence"
        if comparison:
            retrieval_step += " for each company"
        steps.append(retrieval_step)
    steps.extend(["validate evidence coverage", "synthesize and format final answer"])
    return steps


def _route_from_sources(required_sources: list[SourceName]) -> RouteName:
    if required_sources == ["structured"]:
        return "sql"
    if required_sources == ["unstructured"]:
        return "rag"
    return "hybrid"


def _tier_from_plan(
    decision: TierDecision,
    comparison: bool,
    required_sources: list[SourceName],
    document_themes: list[str],
) -> TierName:
    if comparison or len(document_themes) > 2:
        return "deep_research"
    if required_sources == ["structured"]:
        return "sql_fast"
    if required_sources == ["unstructured"]:
        return "rag_fast"
    if required_sources == ["structured", "unstructured"]:
        return "hybrid_fast"
    return decision.tier


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
