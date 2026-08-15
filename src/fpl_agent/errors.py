"""Stable exit codes and closed warning/error codes for the FPL agent."""

from __future__ import annotations

from enum import IntEnum, StrEnum


class ExitCode(IntEnum):
    SUCCESS = 0
    INVALID_CONFIG = 2
    INSUFFICIENT_OR_STALE_TEAM_STATE = 3
    UPSTREAM_DATA_FAILURE = 4
    OPENAI_OR_STRUCTURED_OUTPUT_FAILURE = 5
    PUBLISHING_FAILURE = 6
    COST_GUARD = 7
    UNSUPPORTED_SEASON_RULES = 8


class AgentErrorCode(StrEnum):
    INVALID_CONFIGURATION = "invalid_configuration"
    INSUFFICIENT_TEAM_STATE = "insufficient_team_state"
    STALE_TEAM_STATE = "stale_team_state"
    FPL_UNAVAILABLE = "fpl_unavailable"
    SCHEMA_DRIFT = "schema_drift"
    OPENAI_FAILURE = "openai_failure"
    PUBLISHING_FAILURE = "publishing_failure"
    COST_GUARD = "cost_guard"
    UNSUPPORTED_SEASON_RULES = "unsupported_season_rules"
    CONDITIONAL_ONLY = "conditional_only"
    MATERIAL_UNREVIEWED_RULE_CHANGE = "material_unreviewed_rule_change"


class AgentError(Exception):
    """Base application error with a stable code and exit mapping."""

    def __init__(
        self,
        message: str,
        *,
        code: AgentErrorCode,
        exit_code: ExitCode,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.exit_code = exit_code
        self.details = details or {}


def exit_code_for(code: AgentErrorCode) -> ExitCode:
    mapping: dict[AgentErrorCode, ExitCode] = {
        AgentErrorCode.INVALID_CONFIGURATION: ExitCode.INVALID_CONFIG,
        AgentErrorCode.INSUFFICIENT_TEAM_STATE: ExitCode.INSUFFICIENT_OR_STALE_TEAM_STATE,
        AgentErrorCode.STALE_TEAM_STATE: ExitCode.INSUFFICIENT_OR_STALE_TEAM_STATE,
        AgentErrorCode.CONDITIONAL_ONLY: ExitCode.INSUFFICIENT_OR_STALE_TEAM_STATE,
        AgentErrorCode.FPL_UNAVAILABLE: ExitCode.UPSTREAM_DATA_FAILURE,
        AgentErrorCode.SCHEMA_DRIFT: ExitCode.UPSTREAM_DATA_FAILURE,
        AgentErrorCode.OPENAI_FAILURE: ExitCode.OPENAI_OR_STRUCTURED_OUTPUT_FAILURE,
        AgentErrorCode.PUBLISHING_FAILURE: ExitCode.PUBLISHING_FAILURE,
        AgentErrorCode.COST_GUARD: ExitCode.COST_GUARD,
        AgentErrorCode.UNSUPPORTED_SEASON_RULES: ExitCode.UNSUPPORTED_SEASON_RULES,
        AgentErrorCode.MATERIAL_UNREVIEWED_RULE_CHANGE: ExitCode.UNSUPPORTED_SEASON_RULES,
    }
    return mapping[code]
