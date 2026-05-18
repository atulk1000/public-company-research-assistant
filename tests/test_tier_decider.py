from agent.tier_decider import decide_tier, extract_companies


def test_simple_metric_question_uses_sql_fast() -> None:
    decision = decide_tier("What was Microsoft revenue in 2024?")

    assert decision.tier == "sql_fast"
    assert decision.route == "sql"
    assert decision.companies == ["MSFT"]


def test_simple_qualitative_question_uses_rag_fast() -> None:
    decision = decide_tier("What risks did Microsoft mention around AI?")

    assert decision.tier == "rag_fast"
    assert decision.route == "rag"
    assert decision.companies == ["MSFT"]


def test_mixed_single_company_question_uses_hybrid_fast() -> None:
    decision = decide_tier("How did Microsoft revenue change and what drove it?")

    assert decision.tier == "hybrid_fast"
    assert decision.route == "hybrid"
    assert decision.companies == ["MSFT"]


def test_comparative_driver_question_uses_deep_research() -> None:
    decision = decide_tier(
        "Compare Nvidia and Microsoft AI revenue drivers over the last two years."
    )

    assert decision.tier == "deep_research"
    assert decision.route == "hybrid"
    assert decision.companies == ["MSFT", "NVDA"] or decision.companies == ["NVDA", "MSFT"]


def test_company_extraction_known_tickers() -> None:
    assert extract_companies("Nvidia") == ["NVDA"]
    assert extract_companies("Microsoft") == ["MSFT"]
    assert extract_companies("Nvidia and Microsoft") == ["MSFT", "NVDA"] or extract_companies(
        "Nvidia and Microsoft"
    ) == ["NVDA", "MSFT"]
