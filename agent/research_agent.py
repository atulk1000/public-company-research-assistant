from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agent.llm_answer import compose_answer
from agent.plan_validator import validate_plan_evidence
from agent.rag_tool import retrieve_evidence
from agent.research_plan import ResearchPlan
from agent.research_planner import create_research_plan, plan_context_question
from agent.scope import decide_scope
from agent.sql_tool import run_sql
from agent.state import AgentState
from agent.tier_decider import TierDecision, decide_tier
from agent.validators import validate_evidence_coverage

AGENT_BUDGETS = {
    "sql_fast": {
        "max_llm_calls": 1,
        "max_sql_queries": 1,
        "max_rag_calls": 0,
        "max_retries": 0,
        "max_chunks_per_company": 0,
    },
    "rag_fast": {
        "max_llm_calls": 2,
        "max_sql_queries": 0,
        "max_rag_calls": 1,
        "max_retries": 0,
        "max_chunks_per_company": 5,
    },
    "hybrid_fast": {
        "max_llm_calls": 2,
        "max_sql_queries": 1,
        "max_rag_calls": 1,
        "max_retries": 0,
        "max_chunks_per_company": 5,
    },
    "deep_research": {
        "max_llm_calls": 5,
        "max_sql_queries": 3,
        "max_rag_calls": 4,
        "max_retries": 2,
        "max_chunks_per_company": 6,
    },
}

EXPANDED_TERMS_BY_TICKER = {
    "NVDA": [
        "artificial intelligence",
        "data center",
        "accelerated computing",
        "generative AI",
        "AI infrastructure",
    ],
    "MSFT": [
        "artificial intelligence",
        "Azure AI",
        "cloud and AI",
        "Copilot",
        "AI infrastructure",
    ],
}
GENERIC_EXPANDED_TERMS = [
    "revenue drivers",
    "growth drivers",
    "management discussion",
    "demand",
    "capital expenditures",
    "R&D",
]

SQLRunner = Callable[[str, list[str] | None], dict]
RAGRetriever = Callable[[str, int, list[str] | None], list[dict]]
AnswerComposer = Callable[[str, str, list[str], dict | None, list[dict] | None], str]
TierDecider = Callable[[str], TierDecision]
ResearchPlanner = Callable[[str], ResearchPlan]


class ResearchAgent:
    def __init__(
        self,
        tier_decider: TierDecider = decide_tier,
        sql_runner: SQLRunner = run_sql,
        rag_retriever: RAGRetriever = retrieve_evidence,
        answer_composer: AnswerComposer = compose_answer,
        research_planner: ResearchPlanner | None = None,
    ):
        self.tier_decider = tier_decider
        self.sql_runner = sql_runner
        self.rag_retriever = rag_retriever
        self.answer_composer = answer_composer
        self.research_planner = research_planner

    def run(self, question: str, live: bool = False, return_trace: bool = False):
        state = self.run_state(question, live=live)
        if return_trace:
            return {"answer": state.final_answer or "", "trace": state.to_trace_dict()}
        return state.final_answer or ""

    def run_state(self, question: str, live: bool = False) -> AgentState:
        state = AgentState(question=question)
        scope_decision = decide_scope(question)
        if not scope_decision.in_scope:
            plan = create_research_plan(question, scope_decision=scope_decision)
            state.research_plan = plan
            state.route = "out_of_scope"
            state.tier = "out_of_scope"
            state.final_answer = (
                f"{plan.refusal_reason} Please ask a question about a US public company's "
                "financial metrics, SEC filings, risks, strategy, or management commentary."
            )
            state.plan_validation = {
                "passed": False,
                "warnings": [plan.refusal_reason] if plan.refusal_reason else [],
                "needs_retry": False,
            }
            state.validation = state.plan_validation
            return state

        decision = self.tier_decider(question)
        plan = (
            self.research_planner(question)
            if self.research_planner
            else create_research_plan(question, decision, scope_decision=scope_decision)
        )
        state.research_plan = plan
        state.tier = plan.tier_hint
        state.route = plan.route_hint
        state.companies = plan.companies
        state.time_window = plan.time_window

        budgets = AGENT_BUDGETS[state.tier]
        route_reasons = [
            plan.rationale,
            f"plan_steps={len(plan.planned_steps)}",
            f"tier={state.tier}",
            f"budget={budgets}",
        ]
        if live:
            state.warnings.append("Live data was resolved and prepared before agent execution.")

        if decision.tier == "deep_research":
            self._run_deep_research(state, route_reasons, budgets)
        else:
            self._run_fast_path(state, route_reasons, budgets)

        state.plan_validation = validate_plan_evidence(plan, state.sql_results, state.rag_results)
        state.validation = validate_evidence_coverage(state)
        state.validation.update(
            {
                "rationale": "; ".join(route_reasons),
                "plan_validation": state.plan_validation,
            }
        )
        state.warnings.extend(state.plan_validation.get("warnings", []))
        state.warnings.extend(state.validation.get("warnings", []))
        state.evidence = self._combined_evidence(state)
        state.final_answer = self._compose_grounded_answer(state, route_reasons)
        return state

    def run_response(self, question: str, mode: str = "cached", live: bool = False) -> dict:
        state = self.run_state(question, live=live)
        rationale = state.validation.get("rationale")
        route_reasons = [f"tier={state.tier}"]
        if rationale:
            route_reasons.append(str(rationale))
        route_reasons.extend(state.validation.get("warnings", []))
        status = "success" if state.route != "out_of_scope" else "out_of_scope"
        return {
            "status": status,
            "mode": mode,
            "route": state.route,
            "route_reasons": route_reasons,
            "structured_evidence": state.sql_results,
            "retrieved_evidence": state.rag_results,
            "answer": state.final_answer,
            "research_plan": state.research_plan.to_trace_dict() if state.research_plan else None,
            "plan_validation": state.plan_validation,
            "agent_trace": state.to_trace_dict(),
        }

    def _run_fast_path(
        self, state: AgentState, route_reasons: list[str], budgets: dict[str, int]
    ) -> None:
        if state.route in {"sql", "hybrid"} and budgets["max_sql_queries"] > 0:
            state.add_tool("sql")
            state.sql_results = self.sql_runner(
                (
                    plan_context_question(state.research_plan, None)
                    if state.research_plan
                    else state.question
                ),
                state.companies or None,
            )

        if state.route in {"rag", "hybrid"} and budgets["max_rag_calls"] > 0:
            state.add_tool("rag")
            top_k = self._top_k(state, budgets)
            state.rag_results = self.rag_retriever(
                (
                    plan_context_question(state.research_plan, None)
                    if state.research_plan
                    else state.question
                ),
                top_k,
                state.companies or None,
            )

    def _run_deep_research(
        self, state: AgentState, route_reasons: list[str], budgets: dict[str, int]
    ) -> None:
        sql_calls = 0
        rag_calls = 0

        if state.route in {"sql", "hybrid"} and sql_calls < budgets["max_sql_queries"]:
            state.add_tool("sql")
            state.sql_results = self.sql_runner(
                (
                    plan_context_question(state.research_plan, None)
                    if state.research_plan
                    else state.question
                ),
                state.companies or None,
            )
            sql_calls += 1

        if state.route in {"rag", "hybrid"}:
            for ticker in state.companies or [None]:
                if rag_calls >= budgets["max_rag_calls"]:
                    break
                state.add_tool("rag")
                scope = [ticker] if ticker else None
                retrieval_question = (
                    plan_context_question(state.research_plan, ticker)
                    if state.research_plan
                    else state.question
                )
                state.rag_results.extend(
                    self.rag_retriever(retrieval_question, self._top_k(state, budgets), scope)
                )
                rag_calls += 1

        if state.research_plan:
            state.plan_validation = validate_plan_evidence(
                state.research_plan, state.sql_results, state.rag_results
            )
        state.validation = validate_evidence_coverage(state)
        if state.plan_validation:
            state.validation["plan_validation"] = state.plan_validation
        while (
            (state.plan_validation.get("needs_retry") or state.validation.get("needs_retry"))
            and state.retries < budgets["max_retries"]
            and rag_calls < budgets["max_rag_calls"]
        ):
            missing = (
                state.plan_validation.get("missing_rag_companies")
                or state.validation.get("missing_rag_companies")
                or state.companies
                or []
            )
            if not missing:
                missing = [None]
            for ticker in missing:
                if rag_calls >= budgets["max_rag_calls"]:
                    break
                retry_question = self._expanded_retry_question(
                    (
                        plan_context_question(state.research_plan, ticker)
                        if state.research_plan
                        else state.question
                    ),
                    ticker,
                )
                scope = [ticker] if ticker else None
                state.rag_results.extend(
                    self.rag_retriever(retry_question, self._top_k(state, budgets), scope)
                )
                rag_calls += 1
            state.retries += 1
            if state.research_plan:
                state.plan_validation = validate_plan_evidence(
                    state.research_plan, state.sql_results, state.rag_results
                )
            state.validation = validate_evidence_coverage(state)
            if state.plan_validation:
                state.validation["plan_validation"] = state.plan_validation

    def _compose_grounded_answer(self, state: AgentState, route_reasons: list[str]) -> str:
        evidence_gap_answer = self._evidence_gap_answer(state)
        if evidence_gap_answer:
            return evidence_gap_answer

        answer = self.answer_composer(
            state.question,
            state.route or "hybrid",
            route_reasons + state.validation.get("warnings", []),
            state.sql_results,
            state.rag_results,
        )
        if not state.validation.get("passed", True):
            warning_text = " ".join(state.validation.get("warnings", []))
            if warning_text and warning_text not in answer:
                return f"{answer}\n\nLimitations: {warning_text}"
        return answer

    def _evidence_gap_answer(self, state: AgentState) -> str | None:
        plan = state.research_plan
        if not plan or not plan.in_scope:
            return None

        missing_rag = state.plan_validation.get("missing_rag_companies") or []
        missing_sql = state.plan_validation.get("missing_sql_companies") or []
        no_sql_rows = not (isinstance(state.sql_results, dict) and state.sql_results.get("rows"))
        no_rag_rows = not state.rag_results
        if not ((missing_rag or missing_sql) and no_sql_rows and no_rag_rows):
            return None

        companies = ", ".join(plan.companies) if plan.companies else "the requested company"
        live_hint = "Turn on Live analysis to fetch SEC filings and metrics, then rerun."
        if plan.companies:
            live_hint = (
                f"Turn on Live analysis to fetch {companies} SEC filings and metrics, then rerun."
            )

        return (
            "**Bottom Line**\n\n"
            f"I cannot answer this from cached data because there is no usable evidence loaded for {companies}. "
            "I will not use unrelated company documents to fill that gap.\n\n"
            "**What To Do Next**\n\n"
            f"- {live_hint}\n"
            "- For a forecast, the agent needs recent filings, management guidance, and relevant operating metrics.\n\n"
            "**Caveats**\n\n"
            "- No company-specific evidence was available in cached mode, so no quantitative estimate is provided."
        )

    def _top_k(self, state: AgentState, budgets: dict[str, int]) -> int:
        company_count = max(1, len(state.companies))
        return max(1, budgets["max_chunks_per_company"] * company_count)

    def _combined_evidence(self, state: AgentState) -> list[dict]:
        evidence: list[dict[str, Any]] = []
        if isinstance(state.sql_results, dict):
            for row in state.sql_results.get("rows") or []:
                evidence.append({"type": "sql", "ticker": row.get("ticker"), "row": row})
        for item in state.rag_results:
            evidence.append(
                {
                    "type": "document",
                    "ticker": item.get("metadata", {}).get("ticker"),
                    "source": item.get("source"),
                    "metadata": item.get("metadata", {}),
                }
            )
        return evidence

    def _expanded_retry_question(self, question: str, ticker: str | None) -> str:
        terms = [*GENERIC_EXPANDED_TERMS]
        if ticker:
            terms = [*EXPANDED_TERMS_BY_TICKER.get(ticker, []), *terms]
        return f"{question} {' '.join(terms)}"
