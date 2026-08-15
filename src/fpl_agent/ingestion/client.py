"""HTTP client and FPL route adapters (read-only)."""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict

from fpl_agent.domain.run_state import content_hash_bytes
from fpl_agent.errors import AgentError, AgentErrorCode, ExitCode

ADAPTER_VERSION = "1.0.0"
SCHEMA_VERSION = "2026-27.observed.1"
DEFAULT_BASE = "https://fantasy.premierleague.com/"


class NormalizedSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route: str
    url: str
    retrieved_at: datetime
    http_status: int
    adapter_version: str
    schema_version: str
    content_hash: str
    payload: dict[str, Any]


@dataclass
class ClientLimits:
    connect_timeout: float = 5.0
    read_timeout: float = 20.0
    total_timeout: float = 30.0
    max_bytes: int = 2_000_000
    max_retries: int = 3
    max_requests: int = 40


class FplClient:
    """Read-only FPL HTTP client with budgets and bounded retries."""

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE,
        limits: ClientLimits | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url if base_url.endswith("/") else base_url + "/"
        self.limits = limits or ClientLimits()
        self._requests = 0
        timeout = httpx.Timeout(
            self.limits.total_timeout,
            connect=self.limits.connect_timeout,
            read=self.limits.read_timeout,
        )
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers={"User-Agent": "fpl-agent/0.1 (+read-only; no-auth)"},
            transport=transport,
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> FplClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def get_json(self, route: str, *, required_fields: list[str] | None = None) -> NormalizedSnapshot:
        if self._requests >= self.limits.max_requests:
            raise AgentError(
                "FPL request budget exhausted",
                code=AgentErrorCode.FPL_UNAVAILABLE,
                exit_code=ExitCode.UPSTREAM_DATA_FAILURE,
            )
        last_exc: Exception | None = None
        for attempt in range(self.limits.max_retries + 1):
            self._requests += 1
            try:
                response = self._client.get(route)
            except httpx.HTTPError as exc:
                last_exc = exc
                self._backoff(attempt)
                continue

            ctype = response.headers.get("content-type", "")
            if response.status_code in {401, 403}:
                raise AgentError(
                    f"FPL denied access for {route}: {response.status_code}",
                    code=AgentErrorCode.FPL_UNAVAILABLE,
                    exit_code=ExitCode.UPSTREAM_DATA_FAILURE,
                    details={"status": response.status_code},
                )
            if response.status_code == 404:
                raise AgentError(
                    f"FPL resource not found: {route}",
                    code=AgentErrorCode.FPL_UNAVAILABLE,
                    exit_code=ExitCode.UPSTREAM_DATA_FAILURE,
                    details={"status": 404},
                )
            if response.status_code >= 500:
                last_exc = AgentError(
                    f"FPL upstream {response.status_code}",
                    code=AgentErrorCode.FPL_UNAVAILABLE,
                    exit_code=ExitCode.UPSTREAM_DATA_FAILURE,
                )
                self._backoff(attempt)
                continue
            if "json" not in ctype and response.content[:1] not in (b"{", b"["):
                raise AgentError(
                    f"unexpected content-type for {route}: {ctype}",
                    code=AgentErrorCode.SCHEMA_DRIFT,
                    exit_code=ExitCode.UPSTREAM_DATA_FAILURE,
                )
            raw = response.content
            if len(raw) > self.limits.max_bytes:
                raise AgentError(
                    f"response too large for {route}",
                    code=AgentErrorCode.FPL_UNAVAILABLE,
                    exit_code=ExitCode.UPSTREAM_DATA_FAILURE,
                )
            try:
                payload = response.json()
            except json.JSONDecodeError as exc:
                raise AgentError(
                    f"invalid JSON for {route}",
                    code=AgentErrorCode.SCHEMA_DRIFT,
                    exit_code=ExitCode.UPSTREAM_DATA_FAILURE,
                ) from exc
            if not isinstance(payload, dict):
                # standings/results may be dict with nested lists — allow dict only at top for now
                if isinstance(payload, list):
                    payload = {"items": payload}
                else:
                    raise AgentError(
                        f"unexpected JSON root for {route}",
                        code=AgentErrorCode.SCHEMA_DRIFT,
                        exit_code=ExitCode.UPSTREAM_DATA_FAILURE,
                    )
            if required_fields:
                missing = [f for f in required_fields if f not in payload]
                if missing:
                    raise AgentError(
                        f"schema drift on {route}: missing {missing}",
                        code=AgentErrorCode.SCHEMA_DRIFT,
                        exit_code=ExitCode.UPSTREAM_DATA_FAILURE,
                    )
            return NormalizedSnapshot(
                route=route,
                url=str(response.url),
                retrieved_at=datetime.now(UTC),
                http_status=response.status_code,
                adapter_version=ADAPTER_VERSION,
                schema_version=SCHEMA_VERSION,
                content_hash=content_hash_bytes(raw),
                payload=payload,
            )
        raise AgentError(
            f"FPL request failed after retries: {route}: {last_exc}",
            code=AgentErrorCode.FPL_UNAVAILABLE,
            exit_code=ExitCode.UPSTREAM_DATA_FAILURE,
        )

    def _backoff(self, attempt: int) -> None:
        if attempt >= self.limits.max_retries:
            return
        delay = (2**attempt) * 0.05 + random.uniform(0, 0.05)
        time.sleep(delay)


class BootstrapAdapter:
    REQUIRED = ["events", "elements", "teams", "element_types", "game_settings"]

    def __init__(self, client: FplClient) -> None:
        self.client = client

    def fetch(self) -> NormalizedSnapshot:
        return self.client.get_json("/api/bootstrap-static/", required_fields=self.REQUIRED)


def current_and_next_gameweek(events: list[dict[str, Any]]) -> tuple[int | None, int | None]:
    current = next((e["id"] for e in events if e.get("is_current")), None)
    nxt = next((e["id"] for e in events if e.get("is_next")), None)
    return current, nxt


class EntryAdapter:
    def __init__(self, client: FplClient) -> None:
        self.client = client

    def entry(self, manager_id: int) -> NormalizedSnapshot:
        return self.client.get_json(f"/api/entry/{manager_id}/", required_fields=["id", "name"])

    def history(self, manager_id: int) -> NormalizedSnapshot:
        return self.client.get_json(f"/api/entry/{manager_id}/history/", required_fields=["current"])

    def picks(self, manager_id: int, gw: int) -> NormalizedSnapshot:
        return self.client.get_json(
            f"/api/entry/{manager_id}/event/{gw}/picks/",
            required_fields=["entry_history", "picks"],
        )

    def transfers(self, manager_id: int) -> NormalizedSnapshot:
        return self.client.get_json(f"/api/entry/{manager_id}/transfers/")


class FixturesAdapter:
    def __init__(self, client: FplClient) -> None:
        self.client = client

    def fetch(self) -> NormalizedSnapshot:
        return self.client.get_json("/api/fixtures/")


class LeagueAdapter:
    def __init__(self, client: FplClient) -> None:
        self.client = client

    def standings(self, league_id: int, page: int = 1) -> NormalizedSnapshot:
        return self.client.get_json(
            f"/api/leagues-classic/{league_id}/standings/?page_standings={page}",
            required_fields=["standings"],
        )


class ElementSummaryAdapter:
    def __init__(self, client: FplClient) -> None:
        self.client = client

    def fetch(self, player_id: int) -> NormalizedSnapshot:
        return self.client.get_json(
            f"/api/element-summary/{player_id}/",
            required_fields=["history", "fixtures"],
        )


class LiveAdapter:
    def __init__(self, client: FplClient) -> None:
        self.client = client

    def fetch(self, gw: int) -> NormalizedSnapshot:
        return self.client.get_json(f"/api/event/{gw}/live/", required_fields=["elements"])
