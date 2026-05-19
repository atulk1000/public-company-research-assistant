from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from mcp_server import tools

mcp = FastMCP("Public Company Research Assistant")


@mcp.tool()
def query_financial_metrics(
    ticker: str,
    metrics: list[str] | None = None,
    periods: str | list[str] | None = "latest",
    fiscal_quarter_only: bool = True,
) -> dict:
    """Return governed structured financial metrics for one public-company ticker."""
    return tools.query_financial_metrics(ticker, metrics, periods, fiscal_quarter_only)


@mcp.tool()
def retrieve_filing_context(
    ticker: str,
    topic: str,
    filing_types: list[str] | None = None,
    limit: int = 6,
) -> dict:
    """Retrieve company-scoped SEC filing passages for a topic."""
    return tools.retrieve_filing_context(ticker, topic, filing_types, limit)


@mcp.tool()
def refresh_company_data(
    ticker: str,
    required_sources: list[str] | None = None,
    force_refresh: bool = False,
) -> dict:
    """Resolve and refresh one company's official SEC structured/document data."""
    return tools.refresh_company_data(ticker, required_sources, force_refresh)


@mcp.tool()
def compare_company_metrics(
    tickers: list[str],
    metrics: list[str] | None = None,
    periods: str | list[str] | None = "last_four_quarters",
    fiscal_quarter_only: bool = True,
) -> dict:
    """Return governed structured metrics for up to five public-company tickers."""
    return tools.compare_company_metrics(tickers, metrics, periods, fiscal_quarter_only)


@mcp.tool()
def answer_financial_question(question: str, live_analysis: bool = False) -> dict:
    """Run the existing research agent and return the grounded answer plus trace."""
    return tools.answer_financial_question(question, live_analysis)


@mcp.resource("companies://loaded")
def loaded_companies() -> dict:
    """Companies currently present in the local research store."""
    return tools.loaded_companies_resource()


@mcp.resource("metrics://schema")
def metrics_schema() -> dict:
    """Available structured metric fields and descriptions."""
    return tools.metrics_schema_resource()


@mcp.resource("sources://sec-policy")
def source_policy() -> dict:
    """Current governed SEC source policy."""
    return tools.sources_policy_resource()


@mcp.resource("freshness://companies")
def company_freshness() -> dict:
    """Per-company local refresh timestamps."""
    return tools.freshness_resource()


@mcp.resource("agent://capabilities")
def agent_capabilities() -> dict:
    """Tool list, limits, and guardrails exposed through MCP."""
    return tools.capabilities_resource()


@mcp.prompt()
def public_company_research_question(question: str) -> str:
    return (
        "Answer this as a US public-company financial research task. Use governed "
        "metrics and filing-context tools, cite evidence, and call out missing evidence.\n\n"
        f"Question: {question}"
    )


@mcp.prompt()
def compare_companies(tickers: list[str], topic: str) -> str:
    return (
        "Compare the requested public companies using structured metrics and SEC filing "
        "context where available. Keep the answer concise and evidence-backed.\n\n"
        f"Tickers: {', '.join(tickers)}\nTopic: {topic}"
    )


@mcp.prompt()
def forecast_with_evidence_limits(ticker: str, forecast_question: str) -> str:
    return (
        "Attempt a forecast only from available company guidance, structured metrics, "
        "and SEC-filed evidence. If those inputs are missing, refuse unsupported numeric "
        "forecasting and explain the evidence gap.\n\n"
        f"Ticker: {ticker}\nQuestion: {forecast_question}"
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
