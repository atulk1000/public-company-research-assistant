# Changelog

## Unreleased

- Added an agentic research planning layer that turns questions into structured plans with companies, required metrics, document themes, evidence requirements, and validation checks.
- Added scope guarding for non-public-company-financial questions, including hybrid deterministic/LLM classification.
- Added MAG7 as the default demo company set while allowing the local research library to expand through live analysis.
- Added multi-company live analysis so live-ingested companies can be analyzed together through SQL, RAG, or hybrid workflows.
- Improved answer synthesis with concise analyst-style sections, answer review/revision, numeric citations, and a generated evidence table.
- Added safeguards for missing or irrelevant evidence, including no-row SQL citation handling and refusal to answer from unrelated company documents.
- Expanded SEC source coverage to additional primary filing forms such as insider ownership, beneficial ownership, institutional holdings, proxy, prospectus, tender, and merger filings.
- Added SEC `8-K` / `6-K` `EX-99.*` exhibit ingestion for earnings releases, guidance exhibits, and investor presentations filed with SEC packages.
- Updated Streamlit progress placement and research-plan display.
- Removed the generated SEC company ticker cache from version control and ignored future generated copies.
