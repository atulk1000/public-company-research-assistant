from agent.scope import ScopeDecision, decide_scope, deterministic_scope_decision


def test_deterministic_scope_allows_financial_company_question() -> None:
    decision = deterministic_scope_decision("What risks did Microsoft mention around AI?", ["MSFT"])

    assert decision.in_scope is True
    assert decision.scope == "us_public_company_financial_research"


def test_deterministic_scope_refuses_obvious_unrelated_question() -> None:
    decision = deterministic_scope_decision("Can you write me a pasta recipe?")

    assert decision.in_scope is False
    assert decision.scope == "out_of_scope"


def test_hybrid_scope_uses_llm_for_ambiguous_question(monkeypatch) -> None:
    def fake_llm_scope_decision(question: str, detected_companies: list[str]) -> ScopeDecision:
        return ScopeDecision(
            in_scope=True,
            scope="us_public_company_financial_research",
            confidence=0.7,
            reason="LLM judged this as public-company research.",
            detected_companies=detected_companies,
            used_llm=True,
        )

    monkeypatch.setattr("agent.scope.llm_scope_decision", fake_llm_scope_decision)

    decision = decide_scope("Tell me about Microsoft", [])

    assert decision.in_scope is True
    assert decision.used_llm is True
