from __future__ import annotations

import json

from agent import answer_compose as fallback_answer_compose
from agent.openai_client import get_openai_client
from app.config import get_settings
from app.prompts import ANSWER_SYSTEM_PROMPT, ANSWER_USER_TEMPLATE


def format_structured_evidence(structured_evidence: dict | None, max_rows: int = 10) -> str:
    if not structured_evidence:
        return "None"

    rows = structured_evidence.get("rows", [])
    payload = {
        "mode": structured_evidence.get("mode"),
        "generation_rationale": structured_evidence.get("generation_rationale"),
        "sql": structured_evidence.get("sql"),
        "row_count": len(rows),
        "rows": [
            {
                "citation": f"SQL:{row.get('ticker', 'UNKNOWN')}:{row.get('period_end', 'unknown')}",
                **row,
            }
            for row in rows[:max_rows]
        ],
    }
    return json.dumps(payload, indent=2)


def format_retrieved_evidence(retrieved_evidence: list[dict] | None, max_items: int = 5) -> str:
    if not retrieved_evidence:
        return "None"

    payload = []
    for index, item in enumerate(retrieved_evidence[:max_items], start=1):
        metadata = item.get("metadata", {})
        payload.append(
            {
                "citation": f"DOC:{metadata.get('ticker', 'UNKNOWN')}:{metadata.get('doc_type', 'document')}:{metadata.get('doc_date', 'unknown')}:{index}",
                "score": item.get("score"),
                "text": item.get("text"),
                "metadata": metadata,
            }
        )
    return json.dumps(payload, indent=2)


def compose_answer(question: str, route: str, route_reasons: list[str], structured_evidence: dict | None, retrieved_evidence: list[dict] | None) -> str:
    try:
        settings = get_settings()
        client = get_openai_client()
        response = client.responses.create(
            model=settings.openai_model,
            reasoning={"effort": settings.openai_reasoning_effort},
            instructions=ANSWER_SYSTEM_PROMPT,
            input=ANSWER_USER_TEMPLATE.format(
                question=question,
                route=route,
                route_reasons="; ".join(route_reasons),
                structured_evidence=format_structured_evidence(structured_evidence),
                retrieved_evidence=format_retrieved_evidence(retrieved_evidence),
            ),
        )
        return response.output_text.strip()
    except Exception as exc:
        fallback = fallback_answer_compose.compose_answer(question, route, structured_evidence, retrieved_evidence)
        return (
            f"{fallback}\n\n"
            f"Note: the configured OpenAI model could not complete final synthesis, so this answer used the local fallback composer. "
            f"OpenAI error: {exc}"
        )
