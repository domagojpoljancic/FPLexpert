"""Secret redaction and exit-code mapping."""

from __future__ import annotations

from fpl_agent.errors import AgentErrorCode, ExitCode, exit_code_for
from fpl_agent.observability import redact_mapping, redact_value


def test_redact_by_key_name() -> None:
    data = {"OPENAI_API_KEY": "sk-secret", "team_id": 1}
    out = redact_mapping(data)
    assert out["OPENAI_API_KEY"] == "***REDACTED***"
    assert out["team_id"] == 1


def test_redact_literal_secret() -> None:
    assert "sk-live" not in str(redact_value("token=sk-live", literal_secrets=["sk-live"]))


def test_exit_code_mapping() -> None:
    assert exit_code_for(AgentErrorCode.INVALID_CONFIGURATION) == ExitCode.INVALID_CONFIG
    assert exit_code_for(AgentErrorCode.COST_GUARD) == ExitCode.COST_GUARD
    assert exit_code_for(AgentErrorCode.UNSUPPORTED_SEASON_RULES) == ExitCode.UNSUPPORTED_SEASON_RULES
