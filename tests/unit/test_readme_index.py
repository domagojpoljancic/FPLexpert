"""README latest-results index from report files + price run-log."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fpl_agent.reporting.readme_index import (
    END,
    START,
    list_price_runs,
    list_report_files,
    refresh_readme_recent_runs,
    render_recent_runs_block,
)

NOW = datetime(2026, 8, 18, 19, 0, tzinfo=UTC)


def _write_report(folder: Path, name: str, status: str, headline: str) -> Path:
    path = folder / name
    path.write_text(
        f"# Test\nStatus: **{status}** | Executability: EXECUTABLE\n\n## {headline}\n",
        encoding="utf-8",
    )
    return path


def test_lists_newest_price_and_news_files(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    for i, stamp in enumerate(
        [
            "20260811T190000Z",
            "20260812T190000Z",
            "20260813T190000Z",
            "20260814T190000Z",
            "20260815T190000Z",
            "20260816T190000Z",
            "20260817T190000Z",
            "20260818T190000Z",
        ]
    ):
        _write_report(reports, f"prices-gw1-{stamp}.md", "NO ACTION", f"p{i}")
    _write_report(reports, "predeadline-gw1-20260810T120000Z.md", "WATCH", "old news")
    _write_report(reports, "predeadline-gw1-20260817T120000Z.md", "WATCH", "mid news")
    _write_report(reports, "predeadline-gw1-20260818T120000Z.md", "WATCH", "new news")
    _write_report(reports, "predeadline-gw1-20260809T120000Z.md", "WATCH", "oldest")

    prices = list_price_runs(reports, tmp_path / "missing-log.md", limit=7, now=NOW)
    assert len(prices) == 7
    assert prices[0].rel_path.endswith("20260818T190000Z.md")
    assert prices[-1].rel_path.endswith("20260812T190000Z.md")
    assert "20260811T190000Z" not in prices[-1].rel_path

    news = list_report_files(reports, kind="predeadline", limit=7, now=NOW)
    assert [n.headline for n in news] == ["new news", "mid news"]


def test_parses_new_predeadline_markdown_shape(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "predeadline-gw1-20260818T180000Z.md").write_text(
        "# Pre-deadline FPL review — Gameweek 1\n"
        "\n"
        "Plan: **WATCH**\n"
        "Headline: Watch O'Nien\n"
        "AI: **gpt-5** (live OpenAI).\n"
        "Price watch: **NO ACTION** (overnight rises/falls — not news).\n"
        "\n"
        "## TLDR\n"
        "\n"
        "- Plan: **WATCH**\n"
        "\n"
        "## Do this\n",
        encoding="utf-8",
    )
    news = list_report_files(reports, kind="predeadline", limit=3, now=NOW)
    assert len(news) == 1
    assert news[0].status == "WATCH"
    assert news[0].headline == "Watch O'Nien"


def test_run_log_fills_price_rows_without_files(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    log = tmp_path / "run-log.md"
    log.write_text(
        "# Price watch run log\n\n"
        "| Local (Zagreb) | UTC | GW | Status | Headline |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| 2026-08-18 17:20 CEST | 2026-08-18T15:20Z | 1 | NO ACTION | No price action tonight. |\n",
        encoding="utf-8",
    )
    rows = list_price_runs(reports, log, limit=7, now=NOW)
    assert len(rows) == 1
    assert rows[0].rel_path == "run-log.md"
    assert rows[0].status == "NO ACTION"
    assert rows[0].gameweek == 1


def test_report_file_wins_over_run_log_same_minute(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    _write_report(reports, "prices-gw1-20260818T152044Z.md", "WATCH", "from file")
    log = tmp_path / "run-log.md"
    log.write_text(
        "| x | 2026-08-18T15:20Z | 1 | NO ACTION | from log |\n",
        encoding="utf-8",
    )
    rows = list_price_runs(reports, log, limit=7, now=NOW)
    assert len(rows) == 1
    assert rows[0].rel_path.endswith("prices-gw1-20260818T152044Z.md")
    assert rows[0].status == "WATCH"


def test_refresh_replaces_marked_readme_section(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    _write_report(
        reports,
        "predeadline-gw1-20260818T152951Z.md",
        "WATCH",
        "Watch O'Nien",
    )
    readme = tmp_path / "README.md"
    readme.write_text(
        f"# Title\n\n{START}\nold\n{END}\n\n## After\n",
        encoding="utf-8",
    )
    assert refresh_readme_recent_runs(readme, reports, tmp_path / "run-log.md", now=NOW) is True
    text = readme.read_text(encoding="utf-8")
    assert "Watch O'Nien" in text
    assert "reports/predeadline-gw1-20260818T152951Z.md" in text
    assert text.startswith("# Title\n")
    assert text.endswith("## After\n")
    assert START in text and END in text
    assert "17:29 CEST" in text
    assert "UTC" not in text.split("Latest results", 1)[1].split("<!-- recent-runs:end -->", 1)[0]


def test_refresh_includes_season_plan_link(tmp_path: Path) -> None:
    from fpl_agent.reporting.readme_index import latest_plan_doc_link

    reports = tmp_path / "reports"
    reports.mkdir()
    _write_report(
        reports,
        "predeadline-gw3-20260818T152951Z.md",
        "REVISE",
        "Sell Shaw for De Cuyper",
    )
    (reports / "plan-gw3.md").write_text("# Season plan — Gameweek 3\n", encoding="utf-8")
    assert latest_plan_doc_link(reports) == "reports/plan-gw3.md"
    readme = tmp_path / "README.md"
    readme.write_text(f"# Title\n\n{START}\nold\n{END}\n", encoding="utf-8")
    assert refresh_readme_recent_runs(readme, reports, tmp_path / "run-log.md", now=NOW) is True
    text = readme.read_text(encoding="utf-8")
    assert "**Season plan** (horizon charts)" in text
    assert "[reports/plan-gw3.md](reports/plan-gw3.md)" in text


def test_refresh_skips_readme_without_markers(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("# nope\n", encoding="utf-8")
    assert refresh_readme_recent_runs(readme, tmp_path / "reports") is False
    assert readme.read_text(encoding="utf-8") == "# nope\n"


def test_parses_compact_plan_line_not_this_week_heading(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "predeadline-gw3-20260818T180000Z.md").write_text(
        "# Pre-deadline FPL review — Gameweek 3\n"
        "\n"
        "Plan: **REVISE** — Consider Virgil to Ajayi with the free transfer.\n"
        "AI: **gpt-5.6** (live OpenAI).\n"
        "\n"
        "## Do this\n"
        "\n"
        "- transfer: Virgil to Ajayi\n"
        "\n"
        "## This week\n"
        "\n"
        "- XI (3-5-2): Raya, Ajayi\n",
        encoding="utf-8",
    )
    news = list_report_files(reports, kind="predeadline", limit=3, now=NOW)
    assert len(news) == 1
    assert news[0].status == "REVISE"
    assert news[0].headline == "Consider Virgil to Ajayi with the free transfer."


def test_drops_runs_older_than_seven_days(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    now = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
    _write_report(reports, "predeadline-gw3-20260902T100000Z.md", "REVISE", "Consider Virgil to Ajayi")
    _write_report(reports, "predeadline-gw1-20260821T171955Z.md", "REVISE", "too old")
    news = list_report_files(reports, kind="predeadline", limit=7, now=now)
    assert [n.headline for n in news] == ["Consider Virgil to Ajayi"]


def test_falls_back_to_last_checks_when_window_empty(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    now = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
    _write_report(reports, "prices-gw1-20260810T190000Z.md", "NO ACTION", "old check")
    prices = list_price_runs(reports, tmp_path / "missing-log.md", limit=7, now=now)
    assert len(prices) == 1
    assert prices[0].headline == "old check"


def test_render_empty_lists() -> None:
    block = render_recent_runs_block([], [])
    assert "No price reports yet." in block
    assert "No pre-deadline reports yet." in block
    assert "last 7 days" in block


def test_readme_times_use_cet_cest() -> None:
    from datetime import UTC, datetime

    from fpl_agent.reporting.readme_index import RunLink

    summer = RunLink(
        kind="prices",
        utc=datetime(2026, 8, 18, 15, 20, tzinfo=UTC),
        gameweek=1,
        status="NO ACTION",
        headline="quiet",
        rel_path="run-log.md",
    )
    winter = RunLink(
        kind="predeadline",
        utc=datetime(2026, 1, 15, 15, 20, tzinfo=UTC),
        gameweek=20,
        status="WATCH",
        headline="news",
        rel_path="reports/predeadline-gw20-20260115T152000Z.md",
    )
    block = render_recent_runs_block([summer], [winter])
    assert "18 Aug 17:20 CEST" in block
    assert "15 Jan 16:20 CET" in block
    assert " UTC]" not in block
