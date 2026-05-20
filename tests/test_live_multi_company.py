from dataclasses import dataclass

from agent.company_resolver import ResolvedCompany
from agent.hybrid_tool import answer_question_live_multi_company
from agent.research_planner import create_research_plan


@dataclass
class FakeLiveIngestResult:
    ticker: str
    company_name: str
    used_cache: bool = True
    structured_counts: dict | None = None
    document_counts: dict | None = None
    embedding_counts: dict | None = None
    freshness: dict | None = None

    def __post_init__(self) -> None:
        self.structured_counts = self.structured_counts or {"metric_rows": 1}
        self.document_counts = self.document_counts or {"documents": 1}
        self.embedding_counts = self.embedding_counts or {"updated_chunks": 1}


def test_live_multi_company_resolves_ingests_then_runs_research_agent(monkeypatch) -> None:
    plan = create_research_plan(
        "Compare Microsoft and Alphabet on AI narrative and capex intensity over the last four quarters."
    )
    calls = {"ingest": [], "agent": None}

    def fake_resolve_company(company_name, ticker, clarification=None):
        return ResolvedCompany(status="resolved", ticker=ticker, company_name=ticker, cik="1")

    def fake_run_live_ingestion(resolution, required_sources, progress_callback=None):
        calls["ingest"].append((resolution.ticker, tuple(required_sources)))
        return FakeLiveIngestResult(ticker=resolution.ticker, company_name=resolution.company_name)

    class FakeResearchAgent:
        def __init__(self, research_planner=None):
            self.research_planner = research_planner

        def run_response(self, question: str, mode: str = "cached", live: bool = False):
            planned = self.research_planner(question)
            calls["agent"] = {
                "question": question,
                "mode": mode,
                "live": live,
                "companies": planned.companies,
            }
            return {
                "status": "success",
                "mode": mode,
                "route": planned.route_hint,
                "route_reasons": ["tier=deep_research"],
                "structured_evidence": {
                    "rows": [
                        {"ticker": "MSFT", "period_end": "2026-03-31"},
                        {"ticker": "GOOGL", "period_end": "2026-03-31"},
                    ]
                },
                "retrieved_evidence": [{"metadata": {"ticker": "MSFT"}}],
                "answer": "answer",
                "research_plan": planned.to_trace_dict(),
                "plan_validation": {"passed": True},
                "agent_trace": {
                    "mode": mode,
                    "companies": planned.companies,
                    "tools_used": ["sql", "rag"],
                },
            }

    monkeypatch.setattr("agent.hybrid_tool.resolve_company", fake_resolve_company)
    monkeypatch.setattr("agent.hybrid_tool.run_live_ingestion", fake_run_live_ingestion)
    monkeypatch.setattr("agent.hybrid_tool.ResearchAgent", FakeResearchAgent)

    response = answer_question_live_multi_company("question", plan)

    assert response["status"] == "success"
    assert response["mode"] == "live"
    assert response["route"] == "hybrid"
    assert calls["ingest"] == [
        ("MSFT", ("structured", "unstructured")),
        ("GOOGL", ("structured", "unstructured")),
    ]
    assert calls["agent"] == {
        "question": "question",
        "mode": "live",
        "live": True,
        "companies": ["MSFT", "GOOGL"],
    }
    assert len(response["resolved_companies"]) == 2
    assert len(response["live_ingestions"]) == 2
    assert response["live_ingestion"]["structured_counts"]["metric_rows"] == 2
    assert response["agent_trace"]["live_data_ready"] is True
    assert response["agent_trace"]["live_ingestions"][0]["ticker"] == "MSFT"
