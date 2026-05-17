from __future__ import annotations

MAG7_TICKERS = ("AAPL", "AMZN", "GOOGL", "META", "MSFT", "NVDA", "TSLA")
DEFAULT_DEMO_TICKERS = ",".join(MAG7_TICKERS)
DEFAULT_TARGET_TICKER_FILTER = ""


def parse_target_tickers(raw_value: str | None) -> list[str]:
    value = (raw_value or "").strip()
    return [ticker.strip().upper() for ticker in value.split(",") if ticker.strip()]
