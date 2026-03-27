from __future__ import annotations

from agent.answer_compose import compose_answer
from agent.rag_tool import retrieve_evidence
from agent.router import classify_question
from agent.sql_tool import run_sql


def answer_question(question: str) -> dict:
    decision = classify_question(question)

    structured_evidence = None
    retrieved_evidence = None

    if decision.route in {"sql", "hybrid"}:
        structured_evidence = run_sql(question)
    if decision.route in {"rag", "hybrid"}:
        retrieved_evidence = retrieve_evidence(question)

    answer = compose_answer(question, decision.route, structured_evidence, retrieved_evidence)
    return {
        "route": decision.route,
        "route_reasons": decision.reasons,
        "structured_evidence": structured_evidence,
        "retrieved_evidence": retrieved_evidence,
        "answer": answer,
    }
