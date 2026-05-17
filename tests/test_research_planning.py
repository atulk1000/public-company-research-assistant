from agent.plan_validator import validate_plan_evidence
from agent.research_planner import create_research_plan


def test_comparison_question_creates_hybrid_deep_research_plan() -> None:
    plan = create_research_plan(
        "Compare Microsoft and Alphabet on AI narrative and capex intensity over the last four quarters."
    )

    assert plan.companies == ["MSFT", "GOOGL"] or plan.companies == ["GOOGL", "MSFT"]
    assert plan.comparison is True
    assert plan.time_window == "last_four_quarters"
    assert plan.route_hint == "hybrid"
    assert plan.tier_hint == "deep_research"
    assert "structured" in plan.required_sources
    assert "unstructured" in plan.required_sources
    assert "capex_pct_revenue" in plan.required_metrics
    assert "rd_pct_revenue" in plan.required_metrics
    assert plan.evidence_requirements.minimum_quarters_per_company == 4


def test_plan_validation_flags_missing_company_document_evidence() -> None:
    plan = create_research_plan("Compare Microsoft and Alphabet AI strategy.")
    sql_results = {"rows": [{"ticker": "MSFT"}, {"ticker": "GOOGL"}]}
    rag_results = [
        {
            "text": "Microsoft AI infrastructure and Copilot discussion.",
            "metadata": {"ticker": "MSFT", "doc_type": "10-Q", "doc_date": "2026-04-29"},
        }
    ]

    validation = validate_plan_evidence(plan, sql_results, rag_results)

    assert validation["needs_retry"] is True
    assert "GOOGL" in validation["missing_rag_companies"]


def test_plan_validation_warns_on_null_planned_metric_values() -> None:
    plan = create_research_plan(
        "Compare Microsoft and Alphabet on AI narrative and capex intensity over the last four quarters."
    )
    sql_results = {
        "rows": [
            {
                "ticker": "MSFT",
                "period_end": "2026-03-31",
                "capex_pct_revenue": 0.37,
                "rd_pct_revenue": 0.11,
                "revenue_growth_yoy": 0.18,
            },
            {
                "ticker": "GOOGL",
                "period_end": "2025-09-30",
                "capex_pct_revenue": None,
                "rd_pct_revenue": 0.15,
                "revenue_growth_yoy": 0.16,
            },
        ]
    }

    validation = validate_plan_evidence(plan, sql_results, [])

    assert validation["missing_metric_values"]["GOOGL"] == ["capex_pct_revenue"]
    assert any("GOOGL has null values" in warning for warning in validation["warnings"])


def test_research_agent_response_includes_plan() -> None:
    from agent.research_agent import ResearchAgent

    agent = ResearchAgent(
        sql_runner=lambda question, requested_tickers=None: {
            "rows": [{"ticker": "MSFT", "period_end": "2026-03-31", "revenue": 1}]
        },
        rag_retriever=lambda question, top_k=6, requested_tickers=None: [],
        answer_composer=lambda *args: "answer",
    )

    response = agent.run_response("What was Microsoft revenue?")

    assert response["research_plan"]["companies"] == ["MSFT"]
    assert response["agent_trace"]["research_plan"]["companies"] == ["MSFT"]
    assert "plan_validation" in response


def test_out_of_scope_question_is_refused_before_tools() -> None:
    from agent.research_agent import ResearchAgent

    calls = {"tier": 0, "sql": 0, "rag": 0}

    def tier_decider(question: str):
        calls["tier"] += 1
        raise AssertionError("tier decision should not run for out-of-scope questions")

    def sql_runner(question: str, requested_tickers: list[str] | None = None) -> dict:
        calls["sql"] += 1
        return {"rows": []}

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

    response = agent.run_response("Can you write me a pasta recipe?")

    assert response["status"] == "out_of_scope"
    assert response["route"] == "out_of_scope"
    assert response["research_plan"]["in_scope"] is False
    assert response["research_plan"]["required_sources"] == []
    assert response["research_plan"]["planned_steps"] == [
        "refuse out-of-scope question before tool use"
    ]
    assert calls == {"tier": 0, "sql": 0, "rag": 0}


def test_financial_public_company_question_remains_in_scope() -> None:
    plan = create_research_plan("What risks did Microsoft mention around AI?")

    assert plan.in_scope is True


def test_unloaded_explicit_ticker_is_preserved_in_plan() -> None:
    plan = create_research_plan("Get me next quarter forecast of COIN")

    assert plan.in_scope is True
    assert plan.companies == ["COIN"]
    assert "COIN" in plan.evidence_requirements.rag_companies


def test_cached_answer_refuses_to_use_unrelated_evidence_for_missing_company() -> None:
    from agent.research_agent import ResearchAgent

    calls = {"answer": 0}

    def answer_composer(*args):
        calls["answer"] += 1
        return "should not compose from unrelated evidence"

    agent = ResearchAgent(
        rag_retriever=lambda question, top_k=6, requested_tickers=None: [],
        sql_runner=lambda question, requested_tickers=None: {"rows": []},
        answer_composer=answer_composer,
    )

    response = agent.run_response("Get me next quarter forecast of COIN")

    assert response["research_plan"]["companies"] == ["COIN"]
    assert response["retrieved_evidence"] == []
    assert "no usable evidence loaded for COIN" in response["answer"]
    assert "unrelated company documents" in response["answer"]
    assert calls["answer"] == 0


def test_app_entrypoint_refuses_out_of_scope_questions() -> None:
    from agent.hybrid_tool import answer_question

    response = answer_question("Can you write me a pasta recipe?")

    assert response["status"] == "out_of_scope"
    assert response["structured_evidence"] is None
    assert response["retrieved_evidence"] is None
    assert response["research_plan"]["in_scope"] is False
