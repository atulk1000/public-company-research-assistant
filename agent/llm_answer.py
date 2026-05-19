from __future__ import annotations

import json
import re

from agent import answer_compose as fallback_answer_compose
from agent.openai_client import get_openai_client
from app.config import get_settings
from app.prompts import (
    ANSWER_REVIEW_SYSTEM_PROMPT,
    ANSWER_REVIEW_USER_TEMPLATE,
    ANSWER_SYSTEM_PROMPT,
    ANSWER_USER_TEMPLATE,
)


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


def select_retrieved_evidence(
    retrieved_evidence: list[dict] | None, max_items: int = 8, max_per_ticker: int = 4
) -> list[dict]:
    if not retrieved_evidence:
        return []

    ticker_counts: dict[str, int] = {}
    selected_items = []
    for item in retrieved_evidence:
        metadata = item.get("metadata", {})
        ticker = metadata.get("ticker", "UNKNOWN")
        if ticker_counts.get(ticker, 0) >= max_per_ticker:
            continue
        selected_items.append(item)
        ticker_counts[ticker] = ticker_counts.get(ticker, 0) + 1
        if len(selected_items) >= max_items:
            break

    return selected_items


def format_retrieved_evidence(
    retrieved_evidence: list[dict] | None, max_items: int = 8, max_per_ticker: int = 4
) -> str:
    selected_items = select_retrieved_evidence(retrieved_evidence, max_items, max_per_ticker)
    if not selected_items:
        return "None"

    payload = []
    for index, item in enumerate(selected_items, start=1):
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


def build_evidence_registry(
    structured_evidence: dict | None, retrieved_evidence: list[dict] | None
) -> dict[str, str]:
    registry: dict[str, str] = {}

    if structured_evidence:
        rows = structured_evidence.get("rows", [])
        if not rows:
            for ticker in _extract_tickers_from_structured_evidence(structured_evidence):
                registry[f"SQL:{ticker}:NO_ROWS"] = (
                    f"{ticker} structured query returned no rows for the requested analysis."
                )
        for row in rows:
            ticker = row.get("ticker", "UNKNOWN")
            period_end = row.get("period_end", "unknown")
            label = f"SQL:{ticker}:{period_end}"
            registry[label] = _summarize_sql_row(row)

    for index, item in enumerate(select_retrieved_evidence(retrieved_evidence), start=1):
        metadata = item.get("metadata", {})
        ticker = metadata.get("ticker", "UNKNOWN")
        doc_type = metadata.get("doc_type", "document")
        doc_date = metadata.get("doc_date", "unknown")
        label = f"DOC:{ticker}:{doc_type}:{doc_date}:{index}"
        registry[label] = _summarize_document_item(item)

    return registry


def _summarize_sql_row(row: dict) -> str:
    ticker = row.get("ticker", "UNKNOWN")
    period_end = row.get("period_end", "unknown")
    parts = []
    metric_labels = {
        "capex_pct_revenue": "capex/revenue",
        "rd_pct_revenue": "R&D/revenue",
        "revenue_growth_yoy": "YoY revenue growth",
        "operating_margin": "operating margin",
        "gross_margin": "gross margin",
    }
    for key, label in metric_labels.items():
        value = row.get(key)
        if isinstance(value, int | float):
            parts.append(f"{label} {_format_percent(value)}")
    if not parts and row.get("revenue") is not None:
        parts.append(f"revenue {row.get('revenue')}")
    summary = "; ".join(parts) if parts else "structured metric row"
    return f"{ticker} metrics for {period_end}: {summary}"


def _summarize_document_item(item: dict) -> str:
    metadata = item.get("metadata", {})
    ticker = metadata.get("ticker", "UNKNOWN")
    doc_type = metadata.get("doc_type", "document")
    doc_date = metadata.get("doc_date", "unknown")
    text = " ".join(str(item.get("text", "")).split())
    text = text.replace("•", "").replace("$", "USD ")
    if len(text) > 180:
        text = text[:177].rstrip() + "..."
    return f"{ticker} {doc_type} filed {doc_date}: {text}"


def _format_percent(value: float) -> str:
    return f"{value:.1%}"


COMPARISON_TERMS = ("compare", "comparison", "versus", " vs ", "against", "relative to")


def normalize_answer_markdown(answer: str, question: str | None = None) -> str:
    cleaned = _strip_existing_evidence_used_section((answer or "").strip())
    if not cleaned:
        return ""

    comparison_question = _is_comparison_question(question)
    cleaned = _remove_table_section_heading_rows(cleaned)
    cleaned = re.sub(
        r"\*\*\s*(direct\s+answer|bottom\s+line|comparison\s+snapshot|key\s+takeaways|evidence|what\s+supports\s+this|limitations(?:\s+and\s+inference)?|caveats)\s*\*\*",
        r"\1",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = _force_section_heading_breaks(cleaned)
    cleaned = re.sub(
        r"^\s*(direct\s+answer|bottom\s+line)\s*:?",
        "**Bottom Line**\n\n",
        cleaned,
        count=1,
        flags=re.IGNORECASE,
    )
    middle_heading = "Comparison Snapshot" if comparison_question else "Key Takeaways"
    cleaned = re.sub(
        r"(?im)^\s*(Comparison\s+Snapshot|Key\s+Takeaways)\s*:?",
        f"\n\n**{middle_heading}**\n\n",
        cleaned,
        count=1,
    )
    if f"**{middle_heading}**" not in cleaned:
        cleaned = re.sub(
            r"(?<=[\].])\s+(Comparison\s+Snapshot|Key\s+Takeaways)\s*:?",
            f"\n\n**{middle_heading}**\n\n",
            cleaned,
            count=1,
            flags=re.IGNORECASE,
        )

    cleaned = re.sub(
        r"(?im)^\s*(Evidence(?!\s+Used)|What\s+Supports\s+This)\s*:?",
        "\n\n**What Supports This**\n\n",
        cleaned,
        count=1,
    )
    if "**What Supports This**" not in cleaned:
        cleaned = re.sub(
            r"(?<=[\].])\s+(Evidence(?!\s+Used)|What\s+Supports\s+This)\s*:?",
            "\n\n**What Supports This**\n\n",
            cleaned,
            count=1,
            flags=re.IGNORECASE,
        )

    cleaned = re.sub(
        r"(?im)^\s*(Limitations(?:\s+and\s+inference)?|Caveats)\s*:?",
        "\n\n**Caveats**\n\n",
        cleaned,
        count=1,
    )
    if "**Caveats**" not in cleaned:
        cleaned = re.sub(
            r"(?<=[\].])\s+(Limitations(?:\s+and\s+inference)?|Caveats)\s*:?",
            "\n\n**Caveats**\n\n",
            cleaned,
            count=1,
            flags=re.IGNORECASE,
        )

    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"^\*\*\s*$", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(
        r"\[((?:SQL|DOC):[^\]]+;(?:\s*(?:SQL|DOC):[^\]]+)+)\]", _split_citation_group, cleaned
    )
    cleaned = _reorder_answer_sections(cleaned, comparison_question=comparison_question)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = cleaned.strip()

    if not cleaned.startswith("**Bottom Line**"):
        cleaned = f"**Bottom Line**\n\n{cleaned}"

    return cleaned


def format_answer_for_ui(
    answer: str,
    structured_evidence: dict | None,
    retrieved_evidence: list[dict] | None,
    question: str | None = None,
) -> str:
    normalized = normalize_answer_markdown(_strip_existing_evidence_used_section(answer), question)
    registry = build_evidence_registry(structured_evidence, retrieved_evidence)
    if not registry:
        return normalized

    citation_order: list[str] = []

    def replace_citation(match: re.Match[str]) -> str:
        label = match.group(1)
        registry_label = _resolve_registry_label(label, registry)
        if registry_label is None:
            return match.group(0)
        if registry_label not in citation_order:
            citation_order.append(registry_label)
        return f"[{citation_order.index(registry_label) + 1}]"

    formatted = re.sub(r"\[((?:SQL|DOC):[^\]]+)\]", replace_citation, normalized)
    formatted = _strip_unresolved_raw_citations(formatted)
    formatted = _strip_existing_evidence_used_section(formatted)
    if not citation_order:
        if _has_numbered_citations(formatted):
            return _append_evidence_table(formatted, list(registry.values()))
        return formatted

    return _append_evidence_table(formatted, [registry[label] for label in citation_order])


def _append_evidence_table(answer: str, evidence_rows: list[str]) -> str:
    rows = ["**Evidence Used**", "", "| # | Evidence |", "|---:|---|"]
    for index, evidence in enumerate(evidence_rows, start=1):
        rows.append(f"| {index} | {_markdown_table_cell(evidence)} |")
    return f"{answer.rstrip()}\n\n{chr(10).join(rows)}"


def _has_numbered_citations(answer: str) -> bool:
    return bool(re.search(r"\[\d+\]", answer))


def _force_section_heading_breaks(answer: str) -> str:
    replacements = {
        r"bottom\s+line": "Bottom Line",
        r"comparison\s+snapshot": "Comparison Snapshot",
        r"key\s+takeaways": "Key Takeaways",
        r"what\s+supports\s+this": "What Supports This",
        r"evidence": "What Supports This",
        r"caveats": "Caveats",
        r"limitations(?:\s+and\s+inference)?": "Caveats",
    }
    cleaned = answer
    for pattern, heading in replacements.items():
        cleaned = re.sub(
            rf"(?im)(^|(?<=[\].])\s+|\n+){pattern}\s*:?",
            rf"\n\n**{heading}**\n\n",
            cleaned,
            count=1,
        )
    return cleaned


def _strip_existing_evidence_used_section(answer: str) -> str:
    return re.sub(
        r"(?is)(?:\n|\s)*(?:[-*]\s*)?(?:\*\*)?Evidence Used(?:\*\*)?.*$", "", answer
    ).rstrip()


def split_answer_sections(answer: str) -> list[tuple[str, str]]:
    heading_pattern = re.compile(
        r"(?m)^\*\*(Bottom Line|Comparison Snapshot|Key Takeaways|What Supports This|Caveats|Evidence Used)\*\*\s*$"
    )
    matches = list(heading_pattern.finditer(answer or ""))
    if not matches:
        return []

    sections = []
    for index, match in enumerate(matches):
        heading = match.group(1)
        content_start = match.end()
        content_end = matches[index + 1].start() if index + 1 < len(matches) else len(answer)
        content = answer[content_start:content_end].strip()
        sections.append((heading, content))
    return sections


def _markdown_table_cell(value: str) -> str:
    cleaned = " ".join(str(value).split())
    cleaned = cleaned.replace("|", "/").replace("$", "USD ")
    return cleaned


def _resolve_registry_label(label: str, registry: dict[str, str]) -> str | None:
    if label in registry:
        return label

    # The LLM sometimes cites a document at filing level, e.g.
    # DOC:GOOGL:10-K:2026-02-05, while the formatter registry stores chunk-level
    # labels such as DOC:GOOGL:10-K:2026-02-05:3. Map to the first matching chunk.
    if label.startswith("DOC:"):
        prefix = f"{label}:"
        for candidate in registry:
            if candidate.startswith(prefix):
                return candidate

    if label.startswith("SQL:"):
        parts = label.split(":")
        if len(parts) >= 2:
            no_rows_label = f"SQL:{parts[1]}:NO_ROWS"
            if no_rows_label in registry:
                return no_rows_label

    return None


def _strip_unresolved_raw_citations(answer: str) -> str:
    cleaned = re.sub(r"\[((?:SQL|DOC):[^\]]+)\]", "", answer)
    cleaned = re.sub(r"\s+([,.;:])", r"\1", cleaned)
    return cleaned


def _extract_tickers_from_structured_evidence(structured_evidence: dict) -> list[str]:
    sql = str(structured_evidence.get("sql") or "")
    tickers = []
    for match in re.finditer(r"ticker\s*(?:=|IN)\s*\(?\s*'?([A-Z][A-Z0-9.-]{0,5})", sql):
        ticker = match.group(1).replace(".", "-").upper()
        if ticker not in tickers:
            tickers.append(ticker)
    return tickers or ["UNKNOWN"]


def _split_citation_group(match: re.Match[str]) -> str:
    labels = [label.strip() for label in match.group(1).split(";") if label.strip()]
    return "".join(f"[{label}]" for label in labels)


def _reorder_answer_sections(answer: str, comparison_question: bool = True) -> str:
    middle_heading = "Comparison Snapshot" if comparison_question else "Key Takeaways"
    section_order = [
        "Bottom Line",
        middle_heading,
        "What Supports This",
        "Caveats",
        "Evidence Used",
    ]
    heading_pattern = re.compile(
        r"(?m)^\*\*(Bottom Line|Comparison Snapshot|Key Takeaways|What Supports This|Caveats|Evidence Used)\*\*\s*$"
    )
    matches = list(heading_pattern.finditer(answer))
    if not matches:
        return answer

    preamble = answer[: matches[0].start()].strip()
    sections: dict[str, list[str]] = {heading: [] for heading in section_order}
    for index, match in enumerate(matches):
        heading = match.group(1)
        if heading in {"Comparison Snapshot", "Key Takeaways"}:
            heading = middle_heading
        content_start = match.end()
        content_end = matches[index + 1].start() if index + 1 < len(matches) else len(answer)
        content = answer[content_start:content_end].strip()
        if content:
            sections[heading].append(content)

    _move_embedded_section_content(sections, middle_heading, "What Supports This")
    _move_embedded_section_content(sections, "What Supports This", "Caveats")

    parts = []
    if preamble:
        sections["Bottom Line"].insert(0, preamble)

    for heading in section_order:
        content_parts = sections[heading]
        if content_parts:
            parts.append(f"**{heading}**\n\n" + "\n\n".join(content_parts))

    return "\n\n".join(parts)


def _move_embedded_section_content(
    sections: dict[str, list[str]], source_heading: str, target_heading: str
) -> None:
    updated_source = []
    moved_content = []
    pattern = re.compile(rf"(?im)^\s*\|?\s*\**{re.escape(target_heading)}\**\s*(?:\|\s*)*$")
    for content in sections.get(source_heading, []):
        match = pattern.search(content)
        if not match:
            updated_source.append(content)
            continue
        before = content[: match.start()].strip()
        after = content[match.end() :].strip()
        if before:
            updated_source.append(before)
        if after:
            moved_content.append(after)
    sections[source_heading] = updated_source
    if moved_content:
        sections.setdefault(target_heading, []).extend(moved_content)


def _remove_table_section_heading_rows(answer: str) -> str:
    section_names = ("What Supports This", "Caveats", "Evidence Used", "Key Takeaways")
    cleaned_lines = []
    for line in answer.splitlines():
        normalized = line.replace("|", " ").replace("*", " ")
        normalized = " ".join(normalized.split()).lower()
        if normalized in {section.lower() for section in section_names}:
            cleaned_lines.append(f"**{normalized.title()}**")
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


def _is_comparison_question(question: str | None) -> bool:
    if not question:
        return True
    normalized = f" {question.lower()} "
    return any(term in normalized for term in COMPARISON_TERMS)


def compose_answer(
    question: str,
    route: str,
    route_reasons: list[str],
    structured_evidence: dict | None,
    retrieved_evidence: list[dict] | None,
) -> str:
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
        draft_answer = response.output_text
        try:
            review_response = client.responses.create(
                model=settings.openai_model,
                reasoning={"effort": settings.openai_reasoning_effort},
                instructions=ANSWER_REVIEW_SYSTEM_PROMPT,
                input=ANSWER_REVIEW_USER_TEMPLATE.format(
                    question=question,
                    draft_answer=normalize_answer_markdown(draft_answer, question),
                ),
            )
            final_answer = review_response.output_text
        except Exception:
            final_answer = draft_answer
        return format_answer_for_ui(final_answer, structured_evidence, retrieved_evidence, question)
    except Exception as exc:
        fallback = fallback_answer_compose.compose_answer(
            question, route, structured_evidence, retrieved_evidence
        )
        return format_answer_for_ui(
            f"{fallback}\n\n"
            f"Note: the configured OpenAI model could not complete final synthesis, so this answer used the local fallback composer. "
            f"OpenAI error: {exc}",
            structured_evidence,
            retrieved_evidence,
            question,
        )
