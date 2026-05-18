from agent.llm_answer import (
    format_answer_for_ui,
    format_retrieved_evidence,
    normalize_answer_markdown,
)
from app.prompts import (
    ANSWER_REVIEW_SYSTEM_PROMPT,
    ANSWER_SYSTEM_PROMPT,
    ANSWER_USER_TEMPLATE,
)


def test_answer_prompt_requires_presentable_markdown_sections() -> None:
    expected_sections = [
        "**Bottom Line**",
        "**Comparison Snapshot**",
        "**Key Takeaways**",
        "**What Supports This**",
        "**Caveats**",
    ]

    for section in expected_sections:
        assert section in ANSWER_SYSTEM_PROMPT
        assert section in ANSWER_USER_TEMPLATE

    assert "GitHub-flavored Markdown" in ANSWER_SYSTEM_PROMPT
    assert "user-friendly analyst brief" in ANSWER_SYSTEM_PROMPT
    assert "Do not dump raw result rows" in ANSWER_SYSTEM_PROMPT
    assert "no more than two citation labels" in ANSWER_SYSTEM_PROMPT
    assert "Never combine multiple citation labels inside one bracket" in ANSWER_SYSTEM_PROMPT
    assert "compact Markdown table" in ANSWER_SYSTEM_PROMPT
    assert "Do not use a comparison section for a single-company question" in ANSWER_SYSTEM_PROMPT
    assert "Do not write raw numbered outlines" in ANSWER_SYSTEM_PROMPT
    assert "Evidence Used table" in ANSWER_USER_TEMPLATE
    assert "final answer editor" in ANSWER_REVIEW_SYSTEM_PROMPT


def test_normalize_answer_markdown_repairs_inline_section_labels() -> None:
    raw_answer = (
        "Direct answer\n\n"
        "Microsoft has higher capex intensity. Evidence\n"
        "Microsoft capex was higher. Limitations and inference\n"
        "Alphabet capex is incomplete."
    )

    normalized = normalize_answer_markdown(raw_answer)

    assert normalized.startswith("**Bottom Line**")
    assert "\n\n**What Supports This**\n\n" in normalized
    assert "\n\n**Caveats**\n\n" in normalized
    assert "Limitations and inference" not in normalized


def test_normalize_answer_markdown_does_not_leave_stray_bold_markers() -> None:
    raw_answer = (
        "**Bottom Line**\n\n"
        "Facts from the supplied evidence support the answer.\n\n"
        "**What Supports This**\n\n"
        "- A supported point.\n\n"
        "**Limitations and inference**\n\n"
        "- A limitation."
    )

    normalized = normalize_answer_markdown(raw_answer)

    assert "\n\n**\n\n" not in normalized
    assert normalized.count("**Bottom Line**") == 1
    assert normalized.count("**What Supports This**") == 1
    assert normalized.count("**Caveats**") == 1
    assert "supplied evidence" in normalized


def test_format_retrieved_evidence_balances_companies() -> None:
    evidence = [
        {"text": f"MSFT text {index}", "metadata": {"ticker": "MSFT"}} for index in range(6)
    ] + [{"text": "GOOGL text", "metadata": {"ticker": "GOOGL"}}]

    formatted = format_retrieved_evidence(evidence, max_items=5, max_per_ticker=2)

    assert formatted.count('"ticker": "MSFT"') == 2
    assert formatted.count('"ticker": "GOOGL"') == 1


def test_normalize_answer_markdown_splits_combined_citation_labels() -> None:
    normalized = normalize_answer_markdown(
        "**Bottom Line**\n\n"
        "Microsoft leads on capex [SQL:MSFT:2026-03-31; DOC:MSFT:10-Q:2026-04-29:1]."
    )

    assert "[SQL:MSFT:2026-03-31][DOC:MSFT:10-Q:2026-04-29:1]" in normalized


def test_normalize_answer_markdown_reorders_and_merges_sections() -> None:
    raw_answer = (
        "**Bottom Line**\n\n"
        "Main takeaway.\n\n"
        "**What Supports This**\n\n"
        "Early support sentence.\n\n"
        "**Comparison Snapshot**\n\n"
        "| A | B |\n|---|---|\n| x | y |\n\n"
        "**What Supports This**\n\n"
        "- Later support bullet.\n\n"
        "**Caveats**\n\n"
        "- One caveat."
    )

    normalized = normalize_answer_markdown(raw_answer)

    assert normalized.index("**Comparison Snapshot**") < normalized.index("**What Supports This**")
    assert normalized.count("**What Supports This**") == 1
    assert "Early support sentence" in normalized
    assert "Later support bullet" in normalized


def test_format_answer_for_ui_maps_citations_to_numbered_evidence_table() -> None:
    answer = (
        "**Bottom Line**\n\n"
        "Microsoft capex rose [SQL:MSFT:2026-03-31], and filings tie spend to AI "
        "[DOC:MSFT:10-Q:2026-04-29:1]."
    )
    structured_evidence = {
        "rows": [
            {
                "ticker": "MSFT",
                "period_end": "2026-03-31",
                "capex_pct_revenue": 0.3725,
            }
        ]
    }
    retrieved_evidence = [
        {
            "text": "Cost of revenue increased due to investments in AI infrastructure.",
            "metadata": {"ticker": "MSFT", "doc_type": "10-Q", "doc_date": "2026-04-29"},
        }
    ]

    formatted = format_answer_for_ui(answer, structured_evidence, retrieved_evidence)

    assert "[SQL:MSFT" not in formatted
    assert "[DOC:MSFT" not in formatted
    assert "Microsoft capex rose [1]" in formatted
    assert "tie spend to AI [2]" in formatted
    assert "**Evidence Used**" in formatted
    assert "| 1 | MSFT metrics for 2026-03-31: capex/revenue 37.2% |" in formatted
    assert "| 2 | MSFT 10-Q filed 2026-04-29:" in formatted


def test_format_answer_for_ui_keeps_evidence_table_as_markdown_table() -> None:
    answer = (
        "Bottom Line Microsoft capex rose [SQL:MSFT:2026-03-31]. "
        "Comparison Snapshot\n\n"
        "| Company | Metric |\n"
        "|---|---|\n"
        "| Microsoft | ~37% [SQL:MSFT:2026-03-31] |\n"
        "What Supports This\n"
        "- Microsoft filings tie spending to AI [DOC:MSFT:10-Q:2026-04-29:1].\n"
        "Caveats\n"
        "- Limited data."
    )
    structured_evidence = {
        "rows": [
            {
                "ticker": "MSFT",
                "period_end": "2026-03-31",
                "capex_pct_revenue": 0.3725,
            }
        ]
    }
    retrieved_evidence = [
        {
            "text": "Cost of revenue increased $680 million or 12% due to AI infrastructure.",
            "metadata": {"ticker": "MSFT", "doc_type": "10-Q", "doc_date": "2026-04-29"},
        }
    ]

    formatted = format_answer_for_ui(answer, structured_evidence, retrieved_evidence)

    assert "| What Supports This |" not in formatted
    assert formatted.index("**Comparison Snapshot**") < formatted.index("**What Supports This**")
    assert "\n\n**Evidence Used**\n\n| # | Evidence |\n|---:|---|" in formatted
    assert "USD 680" in formatted


def test_format_answer_for_ui_maps_filing_level_doc_citations() -> None:
    answer = (
        "**Bottom Line**\n\n"
        "Alphabet discusses Gemini [DOC:GOOGL:10-K:2026-02-05].\n\n"
        "Evidence Used | # | Evidence | |---:|---| | 1 | stale model table |"
    )
    retrieved_evidence = [
        {
            "text": "Gemini is Alphabet's frontier AI model.",
            "metadata": {"ticker": "GOOGL", "doc_type": "10-K", "doc_date": "2026-02-05"},
        }
    ]

    formatted = format_answer_for_ui(answer, None, retrieved_evidence)

    assert "[DOC:GOOGL" not in formatted
    assert "Alphabet discusses Gemini [1]." in formatted
    assert "stale model table" not in formatted
    assert formatted.count("**Evidence Used**") == 1
    assert "| 1 | GOOGL 10-K filed 2026-02-05:" in formatted


def test_format_answer_for_ui_replaces_comparison_snapshot_for_single_company() -> None:
    answer = (
        "Bottom Line NVIDIA did not provide next-quarter guidance [DOC:NVDA:10-K:2026-02-25]. "
        "Comparison Snapshot\n\n"
        "- Filing content: strategic product discussion, not numeric guidance [DOC:NVDA:10-K:2026-02-25]. "
        "What Supports This\n"
        "- The filing discusses product platforms [DOC:NVDA:10-K:2026-02-25]. "
        "Caveats\n"
        "- No earnings release was supplied."
    )
    retrieved_evidence = [
        {
            "text": "NVIDIA discusses AI Enterprise, Blackwell, Rubin, and product roadmaps.",
            "metadata": {"ticker": "NVDA", "doc_type": "10-K", "doc_date": "2026-02-25"},
        }
    ]

    formatted = format_answer_for_ui(
        answer,
        None,
        retrieved_evidence,
        question="Get me next quarter forecast of NVDA",
    )

    assert "**Comparison Snapshot**" not in formatted
    assert "**Key Takeaways**" in formatted
    assert "[DOC:NVDA" not in formatted
    assert "\n\n**Evidence Used**\n\n| # | Evidence |\n|---:|---|" in formatted


def test_format_answer_for_ui_maps_no_row_sql_citation_and_repairs_sections() -> None:
    answer = (
        "Bottom Line NBIS has no next-quarter forecast in the supplied data "
        "[SQL:NBIS:hybrid][DOC:NBIS:20-F:2026-04-30:1]. Key Takeaways\n\n"
        "- SQL returned zero rows [SQL:NBIS:hybrid]. "
        "What Supports This\n"
        "- The 20-F has risk commentary [DOC:NBIS:20-F:2026-04-30:1]. "
        "Caveats\n"
        "- No guidance was supplied. Evidence Used | # | Evidence | |---:|---| | 1 | stale |"
    )
    structured_evidence = {
        "sql": "SELECT * FROM v_company_period_metrics WHERE ticker = 'NBIS'",
        "rows": [],
    }
    retrieved_evidence = [
        {
            "text": "Risk factors and annual filing commentary, but no quarterly guidance.",
            "metadata": {"ticker": "NBIS", "doc_type": "20-F", "doc_date": "2026-04-30"},
        }
    ]

    formatted = format_answer_for_ui(
        answer,
        structured_evidence,
        retrieved_evidence,
        question="Get me next quarter forecast of NBIS",
    )

    assert "[SQL:NBIS" not in formatted
    assert "[DOC:NBIS" not in formatted
    assert "NBIS structured query returned no rows" in formatted
    assert "\n\n**What Supports This**\n\n" in formatted
    assert "\n\n**Caveats**\n\n" in formatted
    assert "stale" not in formatted
    assert formatted.count("**Evidence Used**") == 1


def test_normalize_answer_markdown_extracts_section_heading_table_rows() -> None:
    raw_answer = (
        "Bottom Line Microsoft has higher capex.\n"
        "Comparison Snapshot\n\n"
        "| Metric | Microsoft | Alphabet |\n"
        "|---|---|---|\n"
        "| Capex | ~37% | ~32% |\n"
        "| What Supports This | | |\n"
        "- Microsoft evidence.\n"
        "Caveats\n"
        "- Data gap."
    )

    normalized = normalize_answer_markdown(raw_answer)

    assert "| What Supports This |" not in normalized
    assert normalized.startswith("**Bottom Line**")
    assert "\n\n**Comparison Snapshot**\n\n" in normalized
    assert "\n\n**What Supports This**\n\n" in normalized
    assert normalized.index("**Comparison Snapshot**") < normalized.index("**What Supports This**")
