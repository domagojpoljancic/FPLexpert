"""Keep README latest-results links in sync with reports/ (and the price run-log)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

DISPLAY_TZ = ZoneInfo("Europe/Zagreb")

START = "<!-- recent-runs:start -->"
END = "<!-- recent-runs:end -->"
RECENT_DAYS = 7
PRICE_LIMIT = 7
NEWS_LIMIT = 7
_FILE_RE = re.compile(r"^(prices|predeadline)-gw(\d+)-(\d{8}T\d{6}Z)\.md$")
_STATUS_RE = re.compile(r"Status:\s*\*\*(.+?)\*\*")
_PLAN_RE = re.compile(r"Plan:\s*\*\*(.+?)\*\*")
_RUNLOG_ROW = re.compile(
    r"^\|\s*[^|]+\|\s*(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z)\s*\|\s*(\d*)\s*\|\s*([^|]+)\|\s*(.*?)\s*\|$"
)


@dataclass(frozen=True)
class RunLink:
    kind: str
    utc: datetime
    gameweek: int | None
    status: str
    headline: str
    rel_path: str


def take_recent(
    rows: list[RunLink],
    *,
    now: datetime,
    days: int = RECENT_DAYS,
    limit: int,
) -> list[RunLink]:
    """Keep the last `days`, capped at `limit`. If that window is empty, last `limit` checks."""
    ordered = sorted(rows, key=lambda r: r.utc, reverse=True)
    cutoff = now.astimezone(UTC) - timedelta(days=days)
    in_window = [row for row in ordered if row.utc >= cutoff][:limit]
    if in_window:
        return in_window
    return ordered[:limit]


def refresh_readme_recent_runs(
    readme: Path = Path("README.md"),
    reports_dir: Path = Path("reports"),
    run_log: Path = Path("run-log.md"),
    *,
    now: datetime | None = None,
) -> bool:
    """Replace the marked README section. Returns False if markers are missing."""
    if not readme.exists():
        return False
    text = readme.read_text(encoding="utf-8")
    if START not in text or END not in text:
        return False
    clock = now or datetime.now(UTC)
    prices = list_price_runs(reports_dir, run_log, limit=PRICE_LIMIT, now=clock)
    news = list_report_files(reports_dir, kind="predeadline", limit=NEWS_LIMIT, now=clock)
    plan_link = latest_plan_doc_link(reports_dir, news=news)
    block = render_recent_runs_block(prices, news, plan_rel_path=plan_link)
    start = text.index(START)
    end = text.index(END) + len(END)
    updated = text[:start] + block + text[end:]
    if updated != text:
        readme.write_text(updated, encoding="utf-8")
    return True


def list_price_runs(
    reports_dir: Path = Path("reports"),
    run_log: Path = Path("run-log.md"),
    *,
    limit: int = PRICE_LIMIT,
    now: datetime | None = None,
) -> list[RunLink]:
    merged: dict[str, RunLink] = {}
    for row in _parse_run_log(run_log):
        merged[minute_key(row.utc)] = row
    for row in list_report_files(reports_dir, kind="prices", limit=None):
        merged[minute_key(row.utc)] = row
    return take_recent(
        list(merged.values()),
        now=now or datetime.now(UTC),
        limit=limit,
    )


def list_report_files(
    reports_dir: Path,
    *,
    kind: str,
    limit: int | None,
    now: datetime | None = None,
) -> list[RunLink]:
    if not reports_dir.is_dir():
        return []
    rows: list[RunLink] = []
    for path in reports_dir.glob(f"{kind}-gw*.md"):
        parsed = _parse_report_path(path)
        if parsed is None or parsed.kind != kind:
            continue
        rows.append(parsed)
    rows.sort(key=lambda r: r.utc, reverse=True)
    if limit is None:
        return rows
    return take_recent(rows, now=now or datetime.now(UTC), limit=limit)


def render_recent_runs_block(
    prices: list[RunLink],
    news: list[RunLink],
    *,
    plan_rel_path: str | None = None,
) -> str:
    lines = [
        START,
        "## Latest results",
        "",
        "**Price watch** (GitHub, 20:00 Zagreb — last 7 days)",
        *_bullets(prices, empty="No price reports yet."),
        "",
        "**Squad news** (pre-deadline — last 7 days)",
        *_bullets(news, empty="No pre-deadline reports yet."),
    ]
    if plan_rel_path:
        lines += [
            "",
            "**Season plan** (horizon charts)",
            f"- [{plan_rel_path}]({plan_rel_path})",
        ]
    lines += [END]
    return "\n".join(lines)


def latest_plan_doc_link(
    reports_dir: Path = Path("reports"),
    news: list[RunLink] | None = None,
) -> str | None:
    """Stable plan-gw{N}.md for the newest pre-deadline GW, if the file exists."""
    rows = news if news is not None else list_report_files(reports_dir, kind="predeadline", limit=1)
    for row in rows:
        if row.gameweek is None:
            continue
        name = f"plan-gw{row.gameweek}.md"
        if (reports_dir / name).is_file():
            return f"reports/{name}"
    # Fall back to any plan-gw*.md (highest GW).
    plans = sorted(reports_dir.glob("plan-gw*.md"), key=lambda p: p.name)
    if not plans:
        return None
    return f"reports/{plans[-1].name}"


def minute_key(utc: datetime) -> str:
    return utc.astimezone(UTC).strftime("%Y%m%dT%H%M")


def _bullets(rows: list[RunLink], *, empty: str) -> list[str]:
    if not rows:
        return [f"- _{empty}_"]
    out: list[str] = []
    for row in rows:
        when = row.utc.astimezone(DISPLAY_TZ).strftime("%d %b %H:%M %Z")
        gw = f"GW{row.gameweek}" if row.gameweek else "GW?"
        status = row.status or "unknown"
        extra = f" — {_clip(row.headline)}" if row.headline else ""
        out.append(f"- [{when}]({row.rel_path}) · {gw} · **{status}**{extra}")
    return out


def _parse_report_path(path: Path) -> RunLink | None:
    match = _FILE_RE.match(path.name)
    if not match:
        return None
    kind, gw_s, stamp = match.group(1), match.group(2), match.group(3)
    utc = datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    return RunLink(
        kind=kind,
        utc=utc,
        gameweek=int(gw_s),
        status=_status_from_md(text),
        headline=_headline_from_md(text),
        rel_path=f"reports/{path.name}",
    )


def _clip(text: str, limit: int = 90) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _status_from_md(text: str) -> str:
    for line in text.splitlines()[:16]:
        found = _STATUS_RE.search(line) or _PLAN_RE.search(line)
        if found:
            return found.group(1).strip()
    return ""


def _headline_from_md(text: str) -> str:
    skip = {
        "act tonight",
        "watch",
        "ignored (why)",
        "freshness",
        "what changed",
        "attention",
        "attention triggers",
        "suggested moves",
        "can you act on transfer advice?",
        "other warnings",
        "uncertainty",
        "sources",
        "sources checked",
        "tldr",
        "do this",
        "why",
        "notes",
        "model decisions",
        "suggested hubs",
        "pages openai returned",
        "search queries",
        "official fpl status fields",
        "squad file",
        "this week",
    }
    for line in text.splitlines()[:40]:
        stripped = line.strip()
        if stripped.lower().startswith("headline:"):
            return stripped.split(":", 1)[1].strip()
        if stripped.lower().startswith("plan:"):
            rest = re.sub(r"^Plan:\s*\*\*[^*]+\*\*\s*[—–\-:]*\s*", "", stripped).strip()
            if rest and rest.lower() not in skip:
                return rest
        if stripped.startswith("## "):
            title = stripped[3:].strip()
            if title.lower() not in skip:
                return title
    return ""


def _parse_run_log(path: Path) -> list[RunLink]:
    if not path.exists():
        return []
    rows: list[RunLink] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _RUNLOG_ROW.match(line.strip())
        if not match:
            continue
        stamp, gw_s, status, headline = match.groups()
        utc = datetime.strptime(stamp, "%Y-%m-%dT%H:%MZ").replace(tzinfo=UTC)
        rows.append(
            RunLink(
                kind="prices",
                utc=utc,
                gameweek=int(gw_s) if gw_s else None,
                status=status.strip(),
                headline=headline.strip(),
                rel_path="run-log.md",
            )
        )
    return rows
