from __future__ import annotations

import os


DEFAULT_SEC_USER_AGENT = "Public Company Research Assistant AdminContact@example.com"


def sec_headers() -> dict[str, str]:
    user_agent = os.getenv("SEC_USER_AGENT", DEFAULT_SEC_USER_AGENT).strip() or DEFAULT_SEC_USER_AGENT
    return {
        "User-Agent": user_agent,
        "Accept-Encoding": "gzip, deflate",
    }
