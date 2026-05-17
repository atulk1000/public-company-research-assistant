from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RouteName = Literal["sql", "rag", "hybrid"]
TierName = Literal["sql_fast", "rag_fast", "hybrid_fast", "deep_research"]
SourceName = Literal["structured", "unstructured"]


class EvidenceRequirements(BaseModel):
    sql_companies: list[str] = Field(default_factory=list)
    rag_companies: list[str] = Field(default_factory=list)
    minimum_quarters_per_company: int | None = None


class ResearchPlan(BaseModel):
    question: str
    in_scope: bool = True
    refusal_reason: str | None = None
    companies: list[str] = Field(default_factory=list)
    comparison: bool = False
    time_window: str | None = None
    required_metrics: list[str] = Field(default_factory=list)
    document_themes: list[str] = Field(default_factory=list)
    required_sources: list[SourceName] = Field(default_factory=list)
    evidence_requirements: EvidenceRequirements = Field(default_factory=EvidenceRequirements)
    validation_checks: list[str] = Field(default_factory=list)
    planned_steps: list[str] = Field(default_factory=list)
    route_hint: RouteName = "hybrid"
    tier_hint: TierName = "hybrid_fast"
    rationale: str = ""

    def to_trace_dict(self) -> dict:
        return self.model_dump()
