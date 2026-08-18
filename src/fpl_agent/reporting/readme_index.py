"""Keep README latest-results links in sync with reports/ (and the price run-log)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

START = "<!-- recent-runs:start -->"
END = "<!-- recent-runs:end -->"
PRICE_LIMIT = 7
NEWS_LIMIT = 3
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


def refresh_readme_recent_runs(
    readme: Path = Path("README.md"),
    reports_dir: Path = Path("reports"),
    run_log: Path = Path("run-log.md"),
) -> bool:
    """Replace the marked README section. Returns False if markers are missing."""
    if not readme.exists():
        return False
    text = readme.read_text(encoding="utf-8")
    if START not in text or END not in text:
        return False
    prices = list_price_runs(reports_dir, run_log, limit=PRICE_LIMIT)
    news = list_report_files(reports_dir, kind="predeadline", limit=NEWS_LIMIT)
    block = render_recent_runs_block(prices, news)
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
) -> list[RunLink]:
    merged: dict[str, RunLink] = {}
    for row in _parse_run_log(run_log):
        merged[minute_key(row.utc)] = row
    for row in list_report_files(reports_dir, kind="prices", limit=None):
        merged[minute_key(row.utc)] = row
    return sorted(merged.values(), key=lambda r: r.utc, reverse=True)[:limit]


def list_report_files(
    reports_dir: Path,
    *,
    kind: str,
    limit: int | None,
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
    return rows[:limit]


def render_recent_runs_block(prices: list[RunLink], news: list[RunLink]) -> str:
    lines = [
        START,
        "## Latest results",
        "",
        "**Price watch** (GitHub, ~21:00 Zagreb)",
        *_bullets(prices, empty="No price reports yet."),
        "",
        "**Squad news** (pre-deadline)",
        *_bullets(news, empty="No pre-deadline reports yet."),
        END,
    ]
    return "\n".join(lines)


def minute_key(utc: datetime) -> str:
    return utc.astimezone(UTC).strftime("%Y%m%dT%H%M")


def _bullets(rows: list[RunLink], *, empty: str) -> list[str]:
    if not rows:
        return [f"- _{empty}_"]
    out: list[str] = []
    for row in rows:
        when = row.utc.astimezone(UTC).strftime("%d %b %H:%M UTC")
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
    }
    for line in text.splitlines()[:24]:
        stripped = line.strip()
        if stripped.lower().startswith("headline:"):
            return stripped.split(":", 1)[1].strip()
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
