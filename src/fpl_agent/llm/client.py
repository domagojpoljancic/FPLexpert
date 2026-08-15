"""Narrow OpenAI Responses API client with injectable fake."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


class DeadlineSynthesis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chosen_scenario_id: str | None
    explanation: str
    comparison_with_roll: str
    alternative_scenario_id: str | None = None
    uncertainty: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    cited_source_ids: list[str] = Field(default_factory=list)


class OpenAIClient(Protocol):
    def synthesize_deadline(self, payload: dict[str, Any]) -> DeadlineSynthesis: ...


@dataclass
class FakeOpenAIClient:
    response: DeadlineSynthesis | None = None
    fail: bool = False

    def synthesize_deadline(self, payload: dict[str, Any]) -> DeadlineSynthesis:
        if self.fail:
            raise RuntimeError("openai unavailable")
        if self.response:
            return self.response
        candidates = payload.get("candidates") or []
        chosen = None
        for c in candidates:
            if c.get("executability") == "EXECUTABLE":
                chosen = c.get("scenario_id")
                break
        return DeadlineSynthesis(
            chosen_scenario_id=chosen,
            explanation="Deterministic fallback ranking used by fake client.",
            comparison_with_roll="See supplied candidate metrics.",
            alternative_scenario_id=candidates[1]["scenario_id"] if len(candidates) > 1 else None,
            uncertainty=list(payload.get("uncertainty") or []),
            conditions=list(payload.get("conditions") or []),
            warnings=[],
            cited_source_ids=[s["claim_id"] for s in payload.get("sources") or [] if "claim_id" in s],
        )


def validate_synthesis(
    synthesis: DeadlineSynthesis,
    *,
    allowed_scenario_ids: set[str],
    allowed_source_ids: set[str],
    executable_ids: set[str],
) -> DeadlineSynthesis:
    warnings = list(synthesis.warnings)
    chosen = synthesis.chosen_scenario_id
    if chosen is not None:
        if chosen not in allowed_scenario_ids:
            warnings.append("model_chose_unknown_scenario")
            chosen = None
        elif chosen not in executable_ids:
            warnings.append("model_chose_non_executable_scenario")
            chosen = None
    bad_sources = [s for s in synthesis.cited_source_ids if s not in allowed_source_ids]
    if bad_sources:
        warnings.append("model_cited_unknown_sources")
    return synthesis.model_copy(update={"chosen_scenario_id": chosen, "warnings": warnings, "cited_source_ids": [s for s in synthesis.cited_source_ids if s in allowed_source_ids]})
