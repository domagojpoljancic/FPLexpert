"""GitHub publishing state machine."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from fpl_agent.domain.run_state import stable_json_hash


class PublishState(StrEnum):
    PREPARED = "prepared"
    REPOSITORY_PUBLISHED = "repository_published"
    ISSUE_PUBLISHED = "issue_published"
    RECONCILED = "reconciled"


class RunBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bundle_id: str
    state: PublishState = PublishState.PREPARED
    manifest: dict[str, Any]
    decision_record: dict[str, Any]
    markdown: str
    issue_ops: list[dict[str, Any]] = Field(default_factory=list)
    input_hash: str
    output_hash: str


def prepare_bundle(
    *,
    manifest: dict[str, Any],
    decision_record: dict[str, Any],
    markdown: str,
    issue_ops: list[dict[str, Any]] | None = None,
) -> RunBundle:
    payload = {"manifest": manifest, "decision": decision_record, "markdown": markdown}
    bid = stable_json_hash(payload)[:24]
    return RunBundle(
        bundle_id=bid,
        state=PublishState.PREPARED,
        manifest=manifest,
        decision_record=decision_record,
        markdown=markdown,
        issue_ops=issue_ops or [],
        input_hash=stable_json_hash(manifest),
        output_hash=stable_json_hash({"md": markdown, "decision": decision_record}),
    )


def advance(bundle: RunBundle, target: PublishState, *, dry_run: bool = True) -> RunBundle:
    order = [
        PublishState.PREPARED,
        PublishState.REPOSITORY_PUBLISHED,
        PublishState.ISSUE_PUBLISHED,
        PublishState.RECONCILED,
    ]
    if order.index(target) < order.index(bundle.state):
        raise ValueError("cannot move publish state backwards")
    if dry_run and target != PublishState.PREPARED:
        return bundle.model_copy(update={"state": PublishState.RECONCILED})
    return bundle.model_copy(update={"state": target})
