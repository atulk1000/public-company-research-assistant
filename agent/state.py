from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class AgentState:
    question: str
    tier: str | None = None
    route: str | None = None
    companies: list[str] = field(default_factory=list)
    time_window: str | None = None
    tools_used: list[str] = field(default_factory=list)
    sql_results: Any | None = None
    rag_results: list[dict] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)
    validation: dict = field(default_factory=dict)
    retries: int = 0
    warnings: list[str] = field(default_factory=list)
    final_answer: str | None = None
    research_plan: Any | None = None
    plan_validation: dict = field(default_factory=dict)

    def add_tool(self, tool_name: str) -> None:
        if tool_name not in self.tools_used:
            self.tools_used.append(tool_name)

    def to_trace_dict(self) -> dict:
        trace = asdict(self)
        trace["sql_results"] = _json_safe(self.sql_results)
        trace["rag_results"] = _json_safe(self.rag_results)
        trace["evidence"] = _json_safe(self.evidence)
        trace["validation"] = _json_safe(self.validation)
        trace["research_plan"] = _json_safe(self.research_plan)
        trace["plan_validation"] = _json_safe(self.plan_validation)
        return trace


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump())
    return str(value)
