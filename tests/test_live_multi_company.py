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


def test_live_multi_company_resolves_ingests_and_analyzes_all_companies(monkeypatch) -> None:
    plan = create_research_plan(
        "Compare Microsoft and Alphabet on AI narrative and capex intensity over the last four quarters."
    )
    calls = {"ingest": [], "sql": None, "rag": None}

    def fake_resolve_company(company_name, ticker, clarification=None):
        return ResolvedCompany(status="resolved", ticker=ticker, company_name=ticker, cik="1")

    def fake_run_live_ingestion(resolution, required_sources, progress_callback=None):
        calls["ingest"].append((resolution.ticker, tuple(required_sources)))
        return FakeLiveIngestResult(ticker=resolution.ticker, company_name=resolution.company_name)

    def fake_run_sql(question, requested_tickers=None):
        calls["sql"] = requested_tickers
        return {
            "rows": [
                {"ticker": "MSFT", "period_end": "2026-03-31", "capex_pct_revenue": 0.37},
                {"ticker": "GOOGL", "period_end": "2026-03-31", "capex_pct_revenue": 0.32},
            ]
        }

    def fake_retrieve_evidence(question, top_k=6, requested_tickers=None):
        calls["rag"] = requested_tickers
        return [
            {
                "text": "Microsoft AI infrastructure.",
                "metadata": {"ticker": "MSFT", "doc_type": "10-Q", "doc_date": "2026-04-29"},
            },
            {
                "text": "Alphabet Gemini AI.",
                "metadata": {"ticker": "GOOGL", "doc_type": "10-K", "doc_date": "2026-02-05"},
            },
        ]

    monkeypatch.setattr("agent.hybrid_tool.resolve_company", fake_resolve_company)
    monkeypatch.setattr("agent.hybrid_tool.run_live_ingestion", fake_run_live_ingestion)
    monkeypatch.setattr("agent.hybrid_tool.run_sql", fake_run_sql)
    monkeypatch.setattr("agent.hybrid_tool.retrieve_evidence", fake_retrieve_evidence)
    monkeypatch.setattr("agent.hybrid_tool.compose_answer", lambda *args: "answer")

    response = answer_question_live_multi_company("question", plan)

    assert response["status"] == "success"
    assert response["mode"] == "live"
    assert response["route"] == "hybrid"
    assert calls["ingest"] == [
        ("MSFT", ("structured", "unstructured")),
        ("GOOGL", ("structured", "unstructured")),
    ]
    assert calls["sql"] == ["MSFT", "GOOGL"]
    assert calls["rag"] == ["MSFT", "GOOGL"]
    assert len(response["resolved_companies"]) == 2
    assert len(response["live_ingestions"]) == 2
    assert response["live_ingestion"]["structured_counts"]["metric_rows"] == 2
