"""README latest-results index from report files + price run-log."""

from __future__ import annotations

from pathlib import Path

from fpl_agent.reporting.readme_index import (
    END,
    START,
    list_price_runs,
    list_report_files,
    refresh_readme_recent_runs,
    render_recent_runs_block,
)


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

    prices = list_price_runs(reports, tmp_path / "missing-log.md", limit=7)
    assert len(prices) == 7
    assert prices[0].rel_path.endswith("20260818T190000Z.md")
    assert prices[-1].rel_path.endswith("20260812T190000Z.md")
    assert "20260811T190000Z" not in prices[-1].rel_path

    news = list_report_files(reports, kind="predeadline", limit=3)
    assert [n.headline for n in news] == ["new news", "mid news", "old news"]


def test_parses_new_predeadline_markdown_shape(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "predeadline-gw1-20260818T180000Z.md").write_text(
        "# Pre-deadline FPL review — Gameweek 1\n"
        "\n"
        "Plan: **WATCH**\n"
        "AI: **gpt-5** (live OpenAI).\n"
        "Price watch: **NO ACTION** (overnight rises/falls — not news).\n"
        "\n"
        "## Can you act on transfer advice?\n"
        "\n"
        "**Yes.** The squad file is fresh enough.\n"
        "\n"
        "## Watch O'Nien\n"
        "\n"
        "## What changed\n",
        encoding="utf-8",
    )
    news = list_report_files(reports, kind="predeadline", limit=3)
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
    rows = list_price_runs(reports, log, limit=7)
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
    rows = list_price_runs(reports, log, limit=7)
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
    assert refresh_readme_recent_runs(readme, reports, tmp_path / "run-log.md") is True
    text = readme.read_text(encoding="utf-8")
    assert "Watch O'Nien" in text
    assert "reports/predeadline-gw1-20260818T152951Z.md" in text
    assert text.startswith("# Title\n")
    assert text.endswith("## After\n")
    assert START in text and END in text


def test_refresh_skips_readme_without_markers(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("# nope\n", encoding="utf-8")
    assert refresh_readme_recent_runs(readme, tmp_path / "reports") is False
    assert readme.read_text(encoding="utf-8") == "# nope\n"


def test_render_empty_lists() -> None:
    block = render_recent_runs_block([], [])
    assert "No price reports yet." in block
    assert "No pre-deadline reports yet." in block
