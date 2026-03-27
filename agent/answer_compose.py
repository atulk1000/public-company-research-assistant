from __future__ import annotations


def compose_answer(question: str, route: str, structured_evidence: dict | None, retrieved_evidence: list[dict] | None) -> str:
    structured_summary = "No structured evidence used."
    if structured_evidence:
        structured_summary = f"Used SQL with {len(structured_evidence.get('rows', []))} sample metric rows."

    retrieved_summary = "No retrieved evidence used."
    if retrieved_evidence:
        sources = ", ".join(item["source"] for item in retrieved_evidence[:2])
        retrieved_summary = f"Used retrieved passages from {sources}."

    return (
        f"Starter answer for: {question}\n\n"
        f"Route selected: {route}.\n"
        f"{structured_summary}\n"
        f"{retrieved_summary}\n\n"
        "This scaffold currently returns deterministic placeholder evidence so the repo has a working shape before live SEC ingestion and LLM synthesis are wired in."
    )
