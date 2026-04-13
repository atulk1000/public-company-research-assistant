from __future__ import annotations

from collections.abc import Callable

from agent.company_resolver import resolve_company
from agent.llm_answer import compose_answer
from agent.planner import plan_question
from agent.rag_tool import retrieve_evidence
from agent.router import classify_question
from agent.sql_tool import run_sql
from ingestion.live_ingest import run_live_ingestion


ProgressCallback = Callable[[str, str], None]


def answer_question_cached(question: str) -> dict:
    decision = classify_question(question)

    structured_evidence = None
    retrieved_evidence = None

    if decision.route in {"sql", "hybrid"}:
        structured_evidence = run_sql(question)
    if decision.route in {"rag", "hybrid"}:
        retrieved_evidence = retrieve_evidence(question)

    answer = compose_answer(
        question,
        decision.route,
        decision.reasons,
        structured_evidence,
        retrieved_evidence,
    )
    return {
        "status": "success",
        "mode": "cached",
        "route": decision.route,
        "route_reasons": decision.reasons,
        "structured_evidence": structured_evidence,
        "retrieved_evidence": retrieved_evidence,
        "answer": answer,
    }


def answer_question_live(
    question: str,
    clarification_response: str | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict:
    plan = plan_question(question, clarification=clarification_response)
    resolution = resolve_company(plan.company_name, plan.ticker, clarification=clarification_response)

    if resolution.status == "ambiguous" and not clarification_response:
        return {
            "status": "clarification_needed",
            "mode": "live",
            "route": plan.route,
            "route_reasons": [plan.reasoning],
            "structured_evidence": None,
            "retrieved_evidence": None,
            "answer": resolution.message,
            "planning": plan.model_dump(),
            "clarification_message": resolution.message,
            "clarification_candidates": [candidate.model_dump() for candidate in resolution.candidates],
        }

    if resolution.status == "ambiguous" and clarification_response:
        return {
            "status": "not_found",
            "mode": "live",
            "route": plan.route,
            "route_reasons": [plan.reasoning],
            "structured_evidence": None,
            "retrieved_evidence": None,
            "answer": "Sorry, we could not confidently identify the company. Please check that it is a valid US-listed public company.",
            "planning": plan.model_dump(),
        }

    if resolution.status != "resolved":
        return {
            "status": "not_found",
            "mode": "live",
            "route": plan.route,
            "route_reasons": [plan.reasoning],
            "structured_evidence": None,
            "retrieved_evidence": None,
            "answer": resolution.message,
            "planning": plan.model_dump(),
        }

    live_result = run_live_ingestion(
        resolution,
        required_sources=plan.required_sources,
        progress_callback=progress_callback,
    )

    route_reasons = [plan.reasoning, f"resolved_company={resolution.ticker}"]
    if live_result.used_cache:
        route_reasons.append("live_ingest=cache_hit")
    else:
        route_reasons.append("live_ingest=refreshed")

    requested_tickers = [resolution.ticker]
    structured_evidence = None
    retrieved_evidence = None

    if plan.route in {"sql", "hybrid"}:
        if progress_callback:
            progress_callback("analysis", "Running structured analysis...")
        structured_evidence = run_sql(question, requested_tickers=requested_tickers)
    if plan.route in {"rag", "hybrid"}:
        if progress_callback:
            progress_callback("analysis", "Retrieving filing evidence...")
        retrieved_evidence = retrieve_evidence(question, requested_tickers=requested_tickers)

    if progress_callback:
        progress_callback("answer", "Preparing final answer...")

    answer = compose_answer(
        question,
        plan.route,
        route_reasons,
        structured_evidence,
        retrieved_evidence,
    )
    return {
        "status": "success",
        "mode": "live",
        "route": plan.route,
        "route_reasons": route_reasons,
        "structured_evidence": structured_evidence,
        "retrieved_evidence": retrieved_evidence,
        "answer": answer,
        "planning": plan.model_dump(),
        "resolved_company": resolution.model_dump(),
        "live_ingestion": {
            "used_cache": live_result.used_cache,
            "structured_counts": live_result.structured_counts,
            "document_counts": live_result.document_counts,
            "embedding_counts": live_result.embedding_counts,
        },
    }


def answer_question(
    question: str,
    live_analysis: bool = False,
    clarification_response: str | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict:
    try:
        if live_analysis:
            return answer_question_live(
                question,
                clarification_response=clarification_response,
                progress_callback=progress_callback,
            )
        return answer_question_cached(question)
    except Exception as exc:
        return {
            "status": "error",
            "mode": "live" if live_analysis else "cached",
            "route": "error",
            "route_reasons": [str(exc)],
            "structured_evidence": None,
            "retrieved_evidence": None,
            "answer": f"Analysis failed: {exc}",
        }
