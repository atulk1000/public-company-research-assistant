def test_hybrid_tool_cached_path_uses_research_agent_trace(monkeypatch) -> None:
    import agent.hybrid_tool as hybrid_tool

    calls = {"agent": 0}

    class FakeResearchAgent:
        def run_response(self, question: str, mode: str = "cached", live: bool = False) -> dict:
            calls["agent"] += 1
            return {
                "status": "success",
                "mode": mode,
                "route": "sql",
                "route_reasons": ["tier=sql_fast"],
                "structured_evidence": {"rows": []},
                "retrieved_evidence": None,
                "answer": f"answered: {question}",
                "research_plan": {"companies": ["MSFT"]},
                "plan_validation": {"passed": True},
                "agent_trace": {"tier": "sql_fast", "companies": ["MSFT"]},
            }

    monkeypatch.setattr(hybrid_tool, "ResearchAgent", FakeResearchAgent)

    result = hybrid_tool.answer_question("What was Microsoft revenue?", return_trace=True)

    assert calls == {"agent": 1}
    assert result["agent_trace"]["tier"] == "sql_fast"
    assert result["research_plan"]["companies"] == ["MSFT"]


def test_hybrid_tool_hides_cached_agent_trace_by_default(monkeypatch) -> None:
    import agent.hybrid_tool as hybrid_tool

    class FakeResearchAgent:
        def run_response(self, question: str, mode: str = "cached", live: bool = False) -> dict:
            return {
                "status": "success",
                "mode": mode,
                "route": "sql",
                "route_reasons": [],
                "structured_evidence": {"rows": []},
                "retrieved_evidence": None,
                "answer": "ok",
                "research_plan": {"companies": ["MSFT"]},
                "plan_validation": {"passed": True},
                "agent_trace": {"tier": "sql_fast"},
            }

    monkeypatch.setattr(hybrid_tool, "ResearchAgent", FakeResearchAgent)

    result = hybrid_tool.answer_question("What was Microsoft revenue?")

    assert "agent_trace" not in result


def test_hybrid_tool_live_trace_wraps_existing_live_workflow(monkeypatch) -> None:
    import agent.hybrid_tool as hybrid_tool

    def fake_live(question, clarification_response=None, progress_callback=None):
        return {
            "status": "success",
            "mode": "live",
            "route": "hybrid",
            "route_reasons": ["live_ingest=cache_hit"],
            "structured_evidence": {"rows": []},
            "retrieved_evidence": [],
            "answer": "ok",
            "research_plan": {"companies": ["MSFT", "NVDA"]},
            "plan_validation": {"passed": True},
            "live_ingestion": {"used_cache": True},
        }

    monkeypatch.setattr(hybrid_tool, "answer_question_live", fake_live)

    result = hybrid_tool.answer_question(
        "Compare Microsoft and Nvidia revenue drivers.",
        live_analysis=True,
        return_trace=True,
    )

    assert result["agent_trace"]["mode"] == "live"
    assert result["agent_trace"]["research_plan"]["companies"] == ["MSFT", "NVDA"]
    assert result["agent_trace"]["live_ingestion"]["used_cache"] is True


def test_single_company_live_ingests_before_research_agent(monkeypatch) -> None:
    from types import SimpleNamespace

    import agent.hybrid_tool as hybrid_tool
    from agent.planner import QuestionPlan

    calls = []

    def fake_create_research_plan(question, *args, **kwargs):
        return SimpleNamespace(in_scope=True, companies=["MSFT"])

    def fake_plan_question(question, clarification=None):
        return QuestionPlan(
            company_name="Microsoft",
            ticker="MSFT",
            route="hybrid",
            required_sources=["structured", "unstructured"],
            reasoning="test live plan",
        )

    def fake_resolve_company(company_name, ticker, clarification=None):
        calls.append("resolve")
        return SimpleNamespace(
            status="resolved",
            ticker="MSFT",
            company_name="Microsoft Corporation",
            cik="0000789019",
            model_dump=lambda: {
                "status": "resolved",
                "ticker": "MSFT",
                "company_name": "Microsoft Corporation",
                "cik": "0000789019",
            },
        )

    def fake_run_live_ingestion(resolution, required_sources, progress_callback=None):
        calls.append(("ingest", tuple(required_sources)))
        return SimpleNamespace(
            ticker=resolution.ticker,
            company_name=resolution.company_name,
            used_cache=False,
            structured_counts={"metric_rows": 4},
            document_counts={"documents": 2},
            embedding_counts={"updated_chunks": 8},
            freshness={"structured_last_refreshed_at": "now"},
        )

    class FakeResearchAgent:
        def run_response(self, question: str, mode: str = "cached", live: bool = False) -> dict:
            calls.append(("agent", mode, live))
            return {
                "status": "success",
                "mode": mode,
                "route": "hybrid",
                "route_reasons": ["tier=hybrid_fast"],
                "structured_evidence": {"rows": [{"ticker": "MSFT"}]},
                "retrieved_evidence": [{"metadata": {"ticker": "MSFT"}}],
                "answer": "agent answer",
                "research_plan": {"companies": ["MSFT"]},
                "plan_validation": {"passed": True},
                "agent_trace": {"mode": mode, "route": "hybrid", "tools_used": ["sql", "rag"]},
            }

    monkeypatch.setattr(hybrid_tool, "create_research_plan", fake_create_research_plan)
    monkeypatch.setattr(hybrid_tool, "plan_question", fake_plan_question)
    monkeypatch.setattr(hybrid_tool, "resolve_company", fake_resolve_company)
    monkeypatch.setattr(hybrid_tool, "run_live_ingestion", fake_run_live_ingestion)
    monkeypatch.setattr(hybrid_tool, "ResearchAgent", FakeResearchAgent)
    monkeypatch.setattr(
        hybrid_tool,
        "run_sql",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("old SQL path used")),
    )
    monkeypatch.setattr(
        hybrid_tool,
        "retrieve_evidence",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("old RAG path used")),
    )

    result = hybrid_tool.answer_question(
        "What does Microsoft say about AI revenue drivers?",
        live_analysis=True,
        return_trace=True,
    )

    assert calls == [
        "resolve",
        ("ingest", ("structured", "unstructured")),
        ("agent", "live", True),
    ]
    assert result["answer"] == "agent answer"
    assert result["live_ingestion"]["used_cache"] is False
    assert result["agent_trace"]["live_data_ready"] is True
    assert result["agent_trace"]["live_ingestion"]["embedding_counts"]["updated_chunks"] == 8
    assert "live_ingest=refreshed" in result["route_reasons"]


def test_single_company_live_hides_agent_trace_by_default(monkeypatch) -> None:
    from types import SimpleNamespace

    import agent.hybrid_tool as hybrid_tool
    from agent.planner import QuestionPlan

    monkeypatch.setattr(
        hybrid_tool,
        "create_research_plan",
        lambda question, *args, **kwargs: SimpleNamespace(in_scope=True, companies=["MSFT"]),
    )
    monkeypatch.setattr(
        hybrid_tool,
        "plan_question",
        lambda question, clarification=None: QuestionPlan(
            company_name="Microsoft",
            ticker="MSFT",
            route="sql",
            required_sources=["structured"],
            reasoning="test live plan",
        ),
    )
    monkeypatch.setattr(
        hybrid_tool,
        "resolve_company",
        lambda company_name, ticker, clarification=None: SimpleNamespace(
            status="resolved",
            ticker="MSFT",
            company_name="Microsoft Corporation",
            cik="0000789019",
            model_dump=lambda: {
                "status": "resolved",
                "ticker": "MSFT",
                "company_name": "Microsoft Corporation",
                "cik": "0000789019",
            },
        ),
    )
    monkeypatch.setattr(
        hybrid_tool,
        "run_live_ingestion",
        lambda resolution, required_sources, progress_callback=None: SimpleNamespace(
            ticker=resolution.ticker,
            company_name=resolution.company_name,
            used_cache=True,
            structured_counts={"metric_rows": 4},
            document_counts={"documents": 0},
            embedding_counts={"updated_chunks": 0},
            freshness={},
        ),
    )

    class FakeResearchAgent:
        def run_response(self, question: str, mode: str = "cached", live: bool = False) -> dict:
            return {
                "status": "success",
                "mode": mode,
                "route": "sql",
                "route_reasons": [],
                "structured_evidence": {"rows": []},
                "retrieved_evidence": None,
                "answer": "ok",
                "research_plan": {"companies": ["MSFT"]},
                "plan_validation": {"passed": True},
                "agent_trace": {"mode": mode},
            }

    monkeypatch.setattr(hybrid_tool, "ResearchAgent", FakeResearchAgent)

    result = hybrid_tool.answer_question("What was Microsoft revenue?", live_analysis=True)

    assert result["mode"] == "live"
    assert result["live_ingestion"]["used_cache"] is True
    assert "agent_trace" not in result


def test_api_passes_return_trace_to_answer_question(monkeypatch) -> None:
    import importlib
    import sys
    from types import SimpleNamespace

    class FakeFastAPI:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda func: func

        def post(self, *args, **kwargs):
            return lambda func: func

    monkeypatch.setitem(sys.modules, "fastapi", SimpleNamespace(FastAPI=FakeFastAPI))
    sys.modules.pop("app.api", None)

    import app.api as api

    api = importlib.reload(api)
    calls = {}

    def fake_answer_question(
        question,
        live_analysis=False,
        clarification_response=None,
        return_trace=False,
    ):
        calls["question"] = question
        calls["live_analysis"] = live_analysis
        calls["clarification_response"] = clarification_response
        calls["return_trace"] = return_trace
        return {"status": "success", "answer": "ok"}

    monkeypatch.setattr(api, "answer_question", fake_answer_question)

    response = api.ask_question(
        api.QuestionRequest(
            question="Compare Microsoft and Nvidia revenue drivers.",
            live_analysis=True,
            clarification_response="MSFT",
            return_trace=True,
        )
    )

    assert response["status"] == "success"
    assert calls == {
        "question": "Compare Microsoft and Nvidia revenue drivers.",
        "live_analysis": True,
        "clarification_response": "MSFT",
        "return_trace": True,
    }
