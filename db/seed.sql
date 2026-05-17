INSERT INTO companies (cik, ticker, name, sector, industry)
VALUES
    ('0000320193', 'AAPL', 'Apple Inc.', 'Technology', 'Consumer Electronics'),
    ('0001018724', 'AMZN', 'Amazon.com, Inc.', 'Consumer Cyclical', 'Internet Retail'),
    ('0001652044', 'GOOGL', 'Alphabet Inc.', 'Technology', 'Internet Content & Information'),
    ('0001326801', 'META', 'Meta Platforms, Inc.', 'Communication Services', 'Internet Content & Information'),
    ('0000789019', 'MSFT', 'Microsoft Corporation', 'Technology', 'Software'),
    ('0001045810', 'NVDA', 'NVIDIA Corporation', 'Technology', 'Semiconductors'),
    ('0001318605', 'TSLA', 'Tesla, Inc.', 'Consumer Cyclical', 'Auto Manufacturers')
ON CONFLICT (ticker) DO NOTHING;
