from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import re
import sys

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.hybrid_tool import answer_question
from ingestion.source_registry import STRUCTURED_SOURCE_LABELS, UNSTRUCTURED_SOURCE_LABELS

MOJIBAKE_REPLACEMENTS = {
    "\u00e2\u0080\u0099": "'",
    "\u00e2\u0080\u009c": '"',
    "\u00e2\u0080\u009d": '"',
    "\u00e2\u0080\u0093": "-",
    "\u00e2\u0080\u0094": "-",
    "\u00c2\u00a0": " ",
}

PROGRESS_STEPS = {
    "resolve": 10,
    "cache": 20,
    "structured": 45,
    "documents": 65,
    "embeddings": 82,
    "analysis": 92,
    "answer": 100,
}


def clean_display_text(text: str) -> str:
    cleaned = text or ""
    for bad, good in MOJIBAKE_REPLACEMENTS.items():
        cleaned = cleaned.replace(bad, good)
    cleaned = re.sub(r"\s+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def format_metric_value(value) -> str:
    if isinstance(value, float):
        if abs(value) <= 1:
            return f"{value:.2%}"
        return f"{value:,.2f}"
    return str(value)


def rows_to_dataframe(rows: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame

    rename_map = {
        "ticker": "Ticker",
        "period_end": "Period End",
        "revenue_growth_yoy": "Revenue Growth YoY",
        "operating_margin": "Operating Margin",
        "capex_pct_revenue": "Capex % Revenue",
        "rd_pct_revenue": "R&D % Revenue",
        "gross_margin": "Gross Margin",
        "capex": "Capex",
        "currency": "Currency",
        "name": "Company",
        "fiscal_year": "Fiscal Year",
        "fiscal_quarter": "Fiscal Quarter",
    }
    frame = frame.rename(columns=rename_map)

    for column in frame.columns:
        if column in {"Revenue Growth YoY", "Operating Margin", "Capex % Revenue", "R&D % Revenue", "Gross Margin"}:
            frame[column] = frame[column].apply(lambda value: None if pd.isna(value) else f"{value:.2%}")
        elif column == "Capex":
            frame[column] = frame[column].apply(lambda value: None if pd.isna(value) else f"{value:,.0f}")

    return frame


def ensure_session_defaults() -> None:
    st.session_state.setdefault("last_result", None)
    st.session_state.setdefault("pending_question", None)
    st.session_state.setdefault("pending_candidates", [])
    st.session_state.setdefault("pending_message", None)
    st.session_state.setdefault("pending_live_analysis", False)


def clear_pending_clarification() -> None:
    st.session_state["pending_question"] = None
    st.session_state["pending_candidates"] = []
    st.session_state["pending_message"] = None
    st.session_state["pending_live_analysis"] = False


def make_progress_reporter():
    status_placeholder = st.empty()
    progress_bar = st.progress(0)

    def reporter(step: str, message: str) -> None:
        progress_bar.progress(PROGRESS_STEPS.get(step, 5))
        status_placeholder.caption(message)

    return reporter, status_placeholder, progress_bar


def run_analysis(question: str, live_analysis: bool, clarification_response: str | None = None) -> None:
    reporter = None
    status_placeholder = None
    progress_bar = None
    if live_analysis:
        reporter, status_placeholder, progress_bar = make_progress_reporter()
    result = answer_question(
        question,
        live_analysis=live_analysis,
        clarification_response=clarification_response,
        progress_callback=reporter,
    )
    if progress_bar is not None and result.get("status") == "success":
        progress_bar.progress(100)
    if status_placeholder is not None and result.get("status") == "success":
        status_placeholder.caption("Analysis complete.")

    st.session_state["last_result"] = result

    if result.get("status") == "clarification_needed":
        st.session_state["pending_question"] = question
        st.session_state["pending_candidates"] = result.get("clarification_candidates", [])
        st.session_state["pending_message"] = result.get("clarification_message")
        st.session_state["pending_live_analysis"] = live_analysis
    else:
        clear_pending_clarification()


def render_status_banner(result: dict) -> None:
    status = result.get("status", "success")
    if status == "clarification_needed":
        st.warning(clean_display_text(result.get("answer", "")))
    elif status == "not_found":
        st.error(clean_display_text(result.get("answer", "")))
    elif status == "error":
        st.error(clean_display_text(result.get("answer", "")))
    elif result.get("mode") == "live":
        st.success("Live analysis completed.")


def render_route_section(result: dict) -> None:
    st.subheader("Analysis Plan")
    route = result.get("route", "unknown")
    route_reasons = result.get("route_reasons", [])
    mode = result.get("mode", "cached")

    planning = result.get("planning") or {}
    resolved_company = result.get("resolved_company") or {}
    live_ingestion = result.get("live_ingestion") or {}

    metric_cols = st.columns(4)
    metric_cols[0].metric("Mode", mode.upper())
    metric_cols[1].metric("Route", route.upper())
    metric_cols[2].metric("Planner Company", planning.get("ticker") or planning.get("company_name") or "n/a")
    metric_cols[3].metric("Resolved Company", resolved_company.get("ticker") or "n/a")

    if mode == "live" and result.get("status") == "success":
        cache_text = "cache hit" if live_ingestion.get("used_cache") else "refreshed"
        st.caption(f"Live ingestion status: {cache_text}")

    if route_reasons:
        for reason in route_reasons:
            st.caption(clean_display_text(str(reason)))


def render_answer_section(result: dict) -> None:
    if result.get("status") != "success":
        return
    st.subheader("Answer")
    answer = clean_display_text(result.get("answer", ""))
    st.markdown(answer or "_No answer returned._")


def render_source_policy() -> None:
    st.info(
        "Current source policy: this version uses official SEC filed data only. "
        "It does not currently use third-party finance sites, blogs, or unofficial transcript aggregators."
    )

    with st.expander("Active data sources"):
        st.markdown("**Structured sources**")
        for label in STRUCTURED_SOURCE_LABELS:
            st.write(f"- {label}")

        st.markdown("**Unstructured sources**")
        for label in UNSTRUCTURED_SOURCE_LABELS:
            st.write(f"- {label}")


def render_structured_evidence(structured_evidence: dict | None) -> None:
    st.subheader("Structured Evidence")

    if not structured_evidence:
        st.info("No structured evidence was used for this question.")
        return

    rows = structured_evidence.get("rows") or []
    metrics_col, mode_col, row_col = st.columns(3)
    with metrics_col:
        st.metric("Rows Returned", len(rows))
    with mode_col:
        st.metric("SQL Mode", structured_evidence.get("mode", "unknown"))
    with row_col:
        st.metric("Distinct Tickers", len({row.get("ticker") for row in rows if row.get("ticker")}))

    rationale = clean_display_text(str(structured_evidence.get("generation_rationale", "")))
    if rationale:
        st.caption(rationale)

    if rows:
        st.dataframe(rows_to_dataframe(rows), width="stretch", hide_index=True)

        by_ticker: dict[str, list[dict]] = defaultdict(list)
        for row in rows:
            by_ticker[row.get("ticker", "Unknown")].append(row)

        with st.expander("Company-by-company metric breakdown"):
            for ticker, ticker_rows in by_ticker.items():
                st.markdown(f"**{ticker}**")
                for row in ticker_rows:
                    period = row.get("period_end", "unknown period")
                    summary_parts = []
                    for key in ("operating_margin", "capex_pct_revenue", "revenue_growth_yoy", "rd_pct_revenue", "capex"):
                        value = row.get(key)
                        if value is not None:
                            label = key.replace("_", " ")
                            summary_parts.append(f"{label}: {format_metric_value(value)}")
                    st.write(f"{period}: " + ", ".join(summary_parts) if summary_parts else str(row))
    else:
        st.info("The SQL tool ran, but it returned no rows.")

    with st.expander("Generated SQL"):
        st.code(structured_evidence.get("sql", "-- no SQL returned --"), language="sql")


def render_retrieved_evidence(retrieved_evidence: list[dict] | None) -> None:
    st.subheader("Retrieved Evidence")

    if not retrieved_evidence:
        st.info("No document passages were used for this question.")
        return

    overview_col, ticker_col, source_col = st.columns(3)
    with overview_col:
        st.metric("Passages", len(retrieved_evidence))
    with ticker_col:
        st.metric(
            "Companies Represented",
            len({item.get("metadata", {}).get("ticker") for item in retrieved_evidence if item.get("metadata", {}).get("ticker")}),
        )
    with source_col:
        st.metric(
            "Doc Types",
            len({item.get("metadata", {}).get("doc_type") for item in retrieved_evidence if item.get("metadata", {}).get("doc_type")}),
        )

    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in retrieved_evidence:
        ticker = item.get("metadata", {}).get("ticker") or "Unknown"
        grouped[ticker].append(item)

    for ticker in sorted(grouped):
        st.markdown(f"**{ticker}**")
        for item in grouped[ticker]:
            metadata = item.get("metadata", {})
            doc_type = metadata.get("doc_type", "document")
            doc_date = metadata.get("doc_date", "unknown date")
            title = clean_display_text(metadata.get("title") or item.get("source", "source"))
            score = item.get("score")
            label = f"{doc_type} | {doc_date} | score {score}"
            with st.expander(label):
                st.caption(title)
                source_url = metadata.get("source_url")
                if source_url:
                    st.markdown(f"[Open source document]({source_url})")
                st.write(clean_display_text(item.get("text", "")))
                st.caption(item.get("source", ""))


def render_live_ingestion(result: dict) -> None:
    live_ingestion = result.get("live_ingestion")
    if not live_ingestion:
        return

    st.subheader("Live Ingestion")
    count_cols = st.columns(4)
    count_cols[0].metric("Cache", "Hit" if live_ingestion.get("used_cache") else "Refresh")
    count_cols[1].metric("Structured Rows", live_ingestion.get("structured_counts", {}).get("metric_rows", 0))
    count_cols[2].metric("Documents", live_ingestion.get("document_counts", {}).get("documents", 0))
    count_cols[3].metric("Embedded Chunks", live_ingestion.get("embedding_counts", {}).get("updated_chunks", 0))

    freshness = live_ingestion.get("freshness") or {}
    if freshness:
        st.caption(
            "Last refreshed: "
            f"structured={freshness.get('structured_last_refreshed_at') or 'n/a'} | "
            f"documents={freshness.get('documents_last_refreshed_at') or 'n/a'} | "
            f"embeddings={freshness.get('embeddings_last_refreshed_at') or 'n/a'}"
        )


def render_debug_section(result: dict) -> None:
    with st.expander("Debug payload"):
        st.json(result)


def render_clarification_panel() -> None:
    if not st.session_state.get("pending_question"):
        return

    st.subheader("Clarification Needed")
    st.info(clean_display_text(st.session_state.get("pending_message") or "Please clarify the company."))
    candidates = st.session_state.get("pending_candidates") or []
    options = [f"{candidate['ticker']} - {candidate['name']}" for candidate in candidates]
    selected = st.selectbox("Possible matches", options=options) if options else ""
    manual = st.text_input("Or type the ticker / full company name")

    if st.button("Continue Live Analysis"):
        clarification = manual.strip() or selected
        run_analysis(
            st.session_state["pending_question"],
            live_analysis=st.session_state.get("pending_live_analysis", True),
            clarification_response=clarification,
        )


st.set_page_config(page_title="Public Company Research Assistant", layout="wide")
ensure_session_defaults()

st.title("Public Company Research Assistant")
st.caption("Hybrid SQL + RAG assistant for public-company narrative-vs-numbers analysis.")
render_source_policy()

default_question = "Compare Microsoft and Alphabet on AI narrative and capex intensity over the last four quarters."
question = st.text_area(
    "Ask a question about any US public company finances",
    value=default_question,
    height=120,
)
live_analysis = st.toggle(
    "Use live analysis",
    value=False,
    help="If off, answer only from companies that are already loaded locally.",
)

if st.button("Run Analysis", type="primary"):
    clear_pending_clarification()
    run_analysis(question, live_analysis=live_analysis)

render_clarification_panel()

result = st.session_state.get("last_result")
if result:
    render_status_banner(result)
    render_route_section(result)
    render_answer_section(result)

    evidence_tab, documents_tab, live_tab, debug_tab = st.tabs(["Metrics", "Documents", "Live", "Debug"])
    with evidence_tab:
        render_structured_evidence(result.get("structured_evidence"))
    with documents_tab:
        render_retrieved_evidence(result.get("retrieved_evidence"))
    with live_tab:
        render_live_ingestion(result)
    with debug_tab:
        render_debug_section(result)
