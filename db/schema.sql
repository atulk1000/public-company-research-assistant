CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS companies (
    company_id SERIAL PRIMARY KEY,
    cik VARCHAR(10) NOT NULL UNIQUE,
    ticker VARCHAR(10) NOT NULL UNIQUE,
    name TEXT NOT NULL,
    sector TEXT,
    industry TEXT
);

CREATE TABLE IF NOT EXISTS filings (
    filing_id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(company_id),
    accession_no TEXT NOT NULL UNIQUE,
    form_type TEXT NOT NULL,
    filing_date DATE NOT NULL,
    fiscal_year INTEGER,
    fiscal_quarter TEXT,
    source_url TEXT
);

CREATE TABLE IF NOT EXISTS facts (
    fact_id BIGSERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(company_id),
    filing_id INTEGER REFERENCES filings(filing_id),
    taxonomy TEXT NOT NULL DEFAULT 'us-gaap',
    concept TEXT NOT NULL,
    unit TEXT,
    value NUMERIC,
    period_start DATE,
    period_end DATE,
    fiscal_year INTEGER,
    fiscal_quarter TEXT,
    filed_date DATE
);

CREATE TABLE IF NOT EXISTS derived_metrics (
    metric_id BIGSERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(company_id),
    period_end DATE NOT NULL,
    fiscal_year INTEGER,
    fiscal_quarter TEXT,
    currency TEXT,
    revenue NUMERIC,
    revenue_growth_yoy NUMERIC,
    gross_margin NUMERIC,
    operating_margin NUMERIC,
    fcf_margin NUMERIC,
    capex NUMERIC,
    capex_pct_revenue NUMERIC,
    rd_pct_revenue NUMERIC,
    sbc_pct_revenue NUMERIC
);

CREATE TABLE IF NOT EXISTS documents (
    document_id BIGSERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(company_id),
    filing_id INTEGER REFERENCES filings(filing_id),
    doc_type TEXT NOT NULL,
    title TEXT NOT NULL,
    doc_date DATE,
    source_url TEXT,
    raw_text TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS document_chunks (
    chunk_id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    company_id INTEGER NOT NULL REFERENCES companies(company_id),
    chunk_index INTEGER NOT NULL,
    section_name TEXT,
    chunk_text TEXT NOT NULL,
    token_count INTEGER,
    embedding VECTOR(1536),
    start_char INTEGER,
    end_char INTEGER
);

CREATE TABLE IF NOT EXISTS company_data_freshness (
    company_id INTEGER PRIMARY KEY REFERENCES companies(company_id) ON DELETE CASCADE,
    structured_last_refreshed_at TIMESTAMPTZ,
    documents_last_refreshed_at TIMESTAMPTZ,
    embeddings_last_refreshed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS qa_eval_set (
    question_id SERIAL PRIMARY KEY,
    question TEXT NOT NULL,
    expected_route TEXT NOT NULL,
    expected_company TEXT,
    expected_period TEXT,
    gold_notes TEXT
);

CREATE TABLE IF NOT EXISTS qa_eval_runs (
    run_id BIGSERIAL PRIMARY KEY,
    question_id INTEGER NOT NULL REFERENCES qa_eval_set(question_id),
    predicted_route TEXT NOT NULL,
    answer TEXT,
    grounded_score NUMERIC,
    citation_score NUMERIC,
    correctness_score NUMERIC,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
