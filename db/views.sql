DROP VIEW IF EXISTS v_company_period_metrics;

CREATE VIEW v_company_period_metrics AS
SELECT
    c.ticker,
    c.name,
    dm.period_end,
    dm.fiscal_year,
    dm.fiscal_quarter,
    dm.currency,
    dm.revenue,
    dm.revenue_growth_yoy,
    dm.gross_margin,
    dm.operating_margin,
    dm.capex,
    dm.capex_pct_revenue,
    dm.rd_pct_revenue
FROM derived_metrics dm
JOIN companies c ON c.company_id = dm.company_id;
