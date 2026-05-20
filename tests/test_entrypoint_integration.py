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
