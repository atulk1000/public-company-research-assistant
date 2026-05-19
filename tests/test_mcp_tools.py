from types import SimpleNamespace

import pytest

from mcp_server import tools


def test_metric_validation_rejects_arbitrary_columns() -> None:
    with pytest.raises(ValueError, match="Unsupported metric"):
        tools.query_financial_metrics("MSFT", metrics=["revenue; drop table facts"])


def test_ticker_validation_rejects_unsafe_input() -> None:
    with pytest.raises(ValueError, match="Invalid ticker"):
        tools.retrieve_filing_context("MSFT;DROP", topic="AI risks")


def test_retrieve_filing_context_filters_to_requested_company(monkeypatch) -> None:
    def fake_retrieve_evidence(question, top_k, requested_tickers):
        return [
            {
                "source": "MSFT_10-Q_1",
                "text": "Microsoft AI risk text",
                "metadata": {"ticker": "MSFT", "doc_type": "10-Q"},
            },
            {
                "source": "AAPL_10-Q_2",
                "text": "Apple unrelated text",
                "metadata": {"ticker": "AAPL", "doc_type": "10-Q"},
            },
        ]

    monkeypatch.setattr(tools, "retrieve_evidence", fake_retrieve_evidence)

    result = tools.retrieve_filing_context("MSFT", "AI risks", filing_types=["10-Q"])

    assert len(result["evidence"]) == 1
    assert result["evidence"][0]["metadata"]["ticker"] == "MSFT"


def test_answer_financial_question_uses_existing_agent(monkeypatch) -> None:
    calls = {}

    def fake_answer_question(question, live_analysis=False, return_trace=False):
        calls["question"] = question
        calls["live_analysis"] = live_analysis
        calls["return_trace"] = return_trace
        return {"status": "success", "route": "hybrid", "answer": "ok"}

    monkeypatch.setattr(tools, "answer_question", fake_answer_question)

    result = tools.answer_financial_question("Compare MSFT and GOOGL", live_analysis=True)

    assert result["status"] == "success"
    assert calls == {
        "question": "Compare MSFT and GOOGL",
        "live_analysis": True,
        "return_trace": True,
    }


def test_refresh_company_data_passes_force_refresh(monkeypatch) -> None:
    calls = {}

    def fake_resolve_company(company_name, ticker):
        return SimpleNamespace(
            status="resolved",
            ticker=ticker,
            company_name="Microsoft Corporation",
            cik="0000789019",
        )

    def fake_run_live_ingestion(resolution, required_sources, force_refresh=False):
        calls["ticker"] = resolution.ticker
        calls["required_sources"] = required_sources
        calls["force_refresh"] = force_refresh
        return SimpleNamespace(
            ticker=resolution.ticker,
            company_name=resolution.company_name,
            used_cache=False,
            structured_counts={"metric_rows": 4},
            document_counts={"documents": 2},
            embedding_counts={"updated_chunks": 8},
            freshness={"structured_refreshed_at": "now"},
        )

    monkeypatch.setattr(tools, "resolve_company", fake_resolve_company)
    monkeypatch.setattr(tools, "run_live_ingestion", fake_run_live_ingestion)

    result = tools.refresh_company_data("MSFT", ["structured"], force_refresh=True)

    assert result["status"] == "success"
    assert calls == {
        "ticker": "MSFT",
        "required_sources": ["structured"],
        "force_refresh": True,
    }


def test_capabilities_expose_governed_limits() -> None:
    capabilities = tools.capabilities_resource()

    assert "query_financial_metrics" in capabilities["tools"]
    assert capabilities["limits"]["max_companies_per_call"] == 5
    assert any("No arbitrary SQL" in guardrail for guardrail in capabilities["guardrails"])


def test_mcp_server_adapter_imports() -> None:
    import mcp_server.server as server

    assert server.mcp is not None
