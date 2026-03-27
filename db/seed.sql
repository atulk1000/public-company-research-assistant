INSERT INTO companies (cik, ticker, name, sector, industry)
VALUES
    ('0000789019', 'MSFT', 'Microsoft Corporation', 'Technology', 'Software'),
    ('0001652044', 'GOOGL', 'Alphabet Inc.', 'Technology', 'Internet Content & Information'),
    ('0001018724', 'AMZN', 'Amazon.com, Inc.', 'Consumer Cyclical', 'Internet Retail')
ON CONFLICT (ticker) DO NOTHING;
