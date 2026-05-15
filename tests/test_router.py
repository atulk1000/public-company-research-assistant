from agent.router import classify_question_fallback


def test_router_fallback_detects_sql_question() -> None:
    decision = classify_question_fallback("Compare revenue growth by quarter")

    assert decision.route in {"sql", "hybrid"}
    assert decision.reasons


def test_router_fallback_detects_rag_question() -> None:
    decision = classify_question_fallback("What risks did management mention?")

    assert decision.route in {"rag", "hybrid"}
    assert decision.reasons
