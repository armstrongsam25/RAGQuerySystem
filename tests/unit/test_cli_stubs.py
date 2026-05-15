"""Unit tests for the `rag` CLI surface.

`ingest`, `query`, `serve`, and `eval` are all real. The discoverability
properties of spec FR-007 acceptance #3 hold: every command is listed by
``rag --help``.
"""

from __future__ import annotations

from typer.testing import CliRunner

from rag.cli.main import app


def test_eval_command_has_documented_help() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["eval", "--help"])
    assert result.exit_code == 0
    assert "--questions" in result.stdout
    assert "--results-jsonl" in result.stdout
    assert "--results-md" in result.stdout


def test_root_help_lists_every_subcommand() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    for command in ("ingest", "query", "serve", "eval"):
        assert command in result.stdout, f"`{command}` missing from --help: {result.stdout!r}"


def test_root_version_flag_prints_package_version() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip(), "version output is empty"


def test_ingest_requires_pdf_path() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["ingest"])
    # Typer exits non-zero on missing required argument.
    assert result.exit_code != 0
    assert "PDF_PATH" in result.stderr or "Missing argument" in result.stderr


def test_query_requires_question() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["query"])
    assert result.exit_code != 0
    assert "QUESTION" in result.stderr or "Missing argument" in result.stderr
