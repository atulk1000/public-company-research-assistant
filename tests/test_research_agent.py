from agent.research_agent import AGENT_BUDGETS, ResearchAgent
from agent.state import AgentState
from agent.tier_decider import TierDecision
from agent.validators import validate_evidence_coverage


def test_sql_fast_does_not_call_rag() -> None:
    calls = {"sql": 0, "rag": 0}

    def tier_decider(question: str) -> TierDecision:
        return TierDecision(
            tier="sql_fast",
            route="sql",
            companies=["MSFT"],
            needs_validation=False,
            max_retries=0,
            rationale="test",
        )

    def sql_runner(question: str, requested_tickers: list[str] | None = None) -> dict:
        calls["sql"] += 1
        return {"rows": [{"ticker": "MSFT", "period_end": "2024-12-31", "revenue": 1}]}

    def rag_retriever(
        question: str, top_k: int = 6, requested_tickers: list[str] | None = None
    ) -> list[dict]:
        calls["rag"] += 1
        return []

    agent = ResearchAgent(
        tier_decider=tier_decider,
        sql_runner=sql_runner,
        rag_retriever=rag_retriever,
        answer_composer=lambda *args: "answer",
    )
    agent.run_state("What was Microsoft revenue in 2024?")

    assert calls == {"sql": 1, "rag": 0}


def test_deep_research_does_not_exceed_max_retries() -> None:
    calls = {"rag": 0}

    def tier_decider(question: str) -> TierDecision:
        return TierDecision(
            tier="deep_research",
            route="hybrid",
            companies=["MSFT", "NVDA"],
            needs_validation=True,
            max_retries=2,
            rationale="test",
        )

    def sql_runner(question: str, requested_tickers: list[str] | None = None) -> dict:
        return {"rows": [{"ticker": "MSFT"}, {"ticker": "NVDA"}]}

    def rag_retriever(
        question: str, top_k: int = 6, requested_tickers: list[str] | None = None
    ) -> list[dict]:
        calls["rag"] += 1
        return []

    agent = ResearchAgent(
        tier_decider=tier_decider,
        sql_runner=sql_runner,
        rag_retriever=rag_retriever,
        answer_composer=lambda *args: "answer",
    )
    state = agent.run_state("Compare Nvidia and Microsoft AI revenue drivers.")

    assert state.retries <= AGENT_BUDGETS["deep_research"]["max_retries"]
    assert calls["rag"] <= AGENT_BUDGETS["deep_research"]["max_rag_calls"]


def test_validator_flags_missing_rag_company_for_retry() -> None:
    state = AgentState(
        question="Compare Nvidia and Microsoft AI revenue drivers.",
        route="hybrid",
        companies=["MSFT", "NVDA"],
        sql_results={"rows": [{"ticker": "MSFT"}, {"ticker": "NVDA"}]},
        rag_results=[
            {
                "source": "MSFT_10K_1",
                "metadata": {"ticker": "MSFT", "doc_type": "10-K", "doc_date": "2024-07-30"},
            }
        ],
    )

    validation = validate_evidence_coverage(state)

    assert validation["needs_retry"] is True
    assert validation["missing_rag_companies"] == ["NVDA"]


def test_validator_passes_with_company_document_evidence() -> None:
    state = AgentState(
        question="Compare Nvidia and Microsoft AI revenue drivers.",
        route="hybrid",
        companies=["MSFT", "NVDA"],
        sql_results={"rows": [{"ticker": "MSFT"}, {"ticker": "NVDA"}]},
        rag_results=[
            {
                "source": "MSFT_10K_1",
                "metadata": {"ticker": "MSFT", "doc_type": "10-K", "doc_date": "2024-07-30"},
            },
            {
                "source": "NVDA_10K_1",
                "metadata": {"ticker": "NVDA", "doc_type": "10-K", "doc_date": "2024-03-15"},
            },
        ],
    )

    validation = validate_evidence_coverage(state)

    assert validation["passed"] is True
    assert validation["needs_retry"] is False
