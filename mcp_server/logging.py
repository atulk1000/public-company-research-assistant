from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any


def emit_tool_log(tool: str, status: str, payload: dict[str, Any] | None = None) -> None:
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool": tool,
        "status": status,
        "payload": payload or {},
    }
    print(json.dumps(record, default=str), file=sys.stderr, flush=True)
