from __future__ import annotations

from collections.abc import Callable

from agent.company_resolver import resolve_company
from agent.planner import plan_question
from agent.research_agent import ResearchAgent
from agent.research_plan import ResearchPlan
from agent.research_planner import create_research_plan
from agent.scope import decide_scope
from ingestion.live_ingest import run_live_ingestion

ProgressCallback = Callable[[str, str], None]


def answer_question_cached(question: str) -> dict:
    return ResearchAgent().run_response(question, mode="cached")


def answer_question_live(
    question: str,
    clarification_response: str | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict:
    research_plan = create_research_plan(question)
    if len(research_plan.companies) > 1:
        return answer_question_live_multi_company(
            question,
            research_plan,
            progress_callback=progress_callback,
        )

    plan = plan_question(question, clarification=clarification_response)
    resolution = resolve_company(
        plan.company_name, plan.ticker, clarification=clarification_response
    )

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
            "clarification_candidates": [
                candidate.model_dump() for candidate in resolution.candidates
            ],
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

    if progress_callback:
        progress_callback("analysis", "Running agentic analysis over prepared data...")

    result = ResearchAgent().run_response(question, mode="live", live=True)
    return _attach_live_metadata(
        result,
        planning=plan.model_dump(),
        resolved_company=resolution.model_dump(),
        live_ingestion=_live_ingest_payload(live_result),
        live_reasons=[
            plan.reasoning,
            f"resolved_company={resolution.ticker}",
            f"live_ingest={'cache_hit' if live_result.used_cache else 'refreshed'}",
        ],
    )


def answer_question_live_multi_company(
    question: str,
    research_plan: ResearchPlan,
    progress_callback: ProgressCallback | None = None,
) -> dict:
    resolutions = []
    for ticker in research_plan.companies:
        if progress_callback:
            progress_callback("resolve", f"Resolving {ticker}...")
        resolution = resolve_company(ticker, ticker)
        if resolution.status != "resolved":
            return {
                "status": "not_found",
                "mode": "live",
                "route": research_plan.route_hint,
                "route_reasons": [
                    research_plan.rationale,
                    f"Could not resolve planned company {ticker}.",
                ],
                "structured_evidence": None,
                "retrieved_evidence": None,
                "answer": (
                    f"Sorry, I could not confidently identify {ticker}. "
                    "Please use valid US-listed company names or tickers."
                ),
                "research_plan": research_plan.to_trace_dict(),
            }
        resolutions.append(resolution)

    live_results = []
    for index, resolution in enumerate(resolutions, start=1):
        if progress_callback:
            progress_callback(
                "cache",
                f"Checking live cache for {resolution.ticker} ({index}/{len(resolutions)})...",
            )
        live_results.append(
            run_live_ingestion(
                resolution,
                required_sources=research_plan.required_sources,
                progress_callback=progress_callback,
            )
        )

    live_reasons = [
        research_plan.rationale,
        f"research_plan=tier:{research_plan.tier_hint}",
        "resolved_companies=" + ",".join(resolution.ticker for resolution in resolutions),
    ]
    live_reasons.extend(
        f"live_ingest:{result.ticker}={'cache_hit' if result.used_cache else 'refreshed'}"
        for result in live_results
    )

    if progress_callback:
        progress_callback("analysis", "Running agentic multi-company analysis...")

    result = ResearchAgent(research_planner=lambda _: research_plan).run_response(
        question, mode="live", live=True
    )
    return _attach_live_metadata(
        result,
        resolved_companies=[resolution.model_dump() for resolution in resolutions],
        live_ingestions=[_live_ingest_payload(result) for result in live_results],
        live_ingestion=_aggregate_live_ingestion(live_results),
        live_reasons=live_reasons,
    )


def _live_ingest_payload(result) -> dict:
    return {
        "ticker": result.ticker,
        "company_name": result.company_name,
        "used_cache": result.used_cache,
        "structured_counts": result.structured_counts,
        "document_counts": result.document_counts,
        "embedding_counts": result.embedding_counts,
        "freshness": result.freshness,
    }


def _attach_live_metadata(
    result: dict,
    *,
    planning: dict | None = None,
    resolved_company: dict | None = None,
    resolved_companies: list[dict] | None = None,
    live_ingestion: dict | None = None,
    live_ingestions: list[dict] | None = None,
    live_reasons: list[str] | None = None,
) -> dict:
    result["mode"] = "live"
    if planning is not None:
        result["planning"] = planning
    if resolved_company is not None:
        result["resolved_company"] = resolved_company
    if resolved_companies is not None:
        result["resolved_companies"] = resolved_companies
    if live_ingestion is not None:
        result["live_ingestion"] = live_ingestion
    if live_ingestions is not None:
        result["live_ingestions"] = live_ingestions

    route_reasons = list(result.get("route_reasons") or [])
    for reason in live_reasons or []:
        if reason and reason not in route_reasons:
            route_reasons.append(reason)
    result["route_reasons"] = route_reasons

    trace = result.setdefault("agent_trace", _trace_from_response(result))
    trace["mode"] = "live"
    trace["live_data_ready"] = True
    if planning is not None:
        trace["planning"] = planning
    if resolved_company is not None:
        trace["resolved_company"] = resolved_company
    if resolved_companies is not None:
        trace["resolved_companies"] = resolved_companies
    if live_ingestion is not None:
        trace["live_ingestion"] = live_ingestion
    if live_ingestions is not None:
        trace["live_ingestions"] = live_ingestions
    return result


def _aggregate_live_ingestion(results: list) -> dict:
    return {
        "used_cache": all(result.used_cache for result in results),
        "companies": [_live_ingest_payload(result) for result in results],
        "structured_counts": {
            "metric_rows": sum(result.structured_counts.get("metric_rows", 0) for result in results)
        },
        "document_counts": {
            "documents": sum(result.document_counts.get("documents", 0) for result in results)
        },
        "embedding_counts": {
            "updated_chunks": sum(
                result.embedding_counts.get("updated_chunks", 0) for result in results
            )
        },
        "freshness": None,
    }


def _trace_from_response(result: dict) -> dict:
    return {
        "mode": result.get("mode"),
        "route": result.get("route"),
        "status": result.get("status"),
        "route_reasons": result.get("route_reasons") or [],
        "research_plan": result.get("research_plan") or result.get("planning"),
        "plan_validation": result.get("plan_validation"),
        "resolved_company": result.get("resolved_company"),
        "resolved_companies": result.get("resolved_companies"),
        "live_ingestion": result.get("live_ingestion"),
        "live_ingestions": result.get("live_ingestions"),
    }


def answer_question(
    question: str,
    live_analysis: bool = False,
    clarification_response: str | None = None,
    progress_callback: ProgressCallback | None = None,
    return_trace: bool = False,
) -> dict:
    try:
        scope_decision = decide_scope(question)
        scope_plan = create_research_plan(question, scope_decision=scope_decision)
        if not scope_plan.in_scope:
            result = {
                "status": "out_of_scope",
                "mode": "live" if live_analysis else "cached",
                "route": "out_of_scope",
                "route_reasons": [scope_plan.refusal_reason or "Question is out of scope."],
                "structured_evidence": None,
                "retrieved_evidence": None,
                "answer": (
                    f"{scope_plan.refusal_reason} Please ask a question about a US public "
                    "company's financial metrics, SEC filings, risks, strategy, or management commentary."
                ),
                "research_plan": scope_plan.to_trace_dict(),
                "plan_validation": {
                    "passed": False,
                    "warnings": [scope_plan.refusal_reason] if scope_plan.refusal_reason else [],
                    "needs_retry": False,
                },
            }
            if return_trace:
                result["agent_trace"] = _trace_from_response(result)
            return result
        if live_analysis:
            result = answer_question_live(
                question,
                clarification_response=clarification_response,
                progress_callback=progress_callback,
            )
            if return_trace:
                result.setdefault("agent_trace", _trace_from_response(result))
            else:
                result.pop("agent_trace", None)
            return result
        result = answer_question_cached(question)
        if not return_trace:
            result.pop("agent_trace", None)
        return result
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
