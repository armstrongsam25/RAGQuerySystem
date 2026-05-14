"""Unit tests for the migration runner's pure functions (spec FR-006)."""

from __future__ import annotations

from pathlib import Path

import pytest

from rag.migrations import list_available, pending


def _make_files(directory: Path, names: list[str]) -> list[Path]:
    paths = []
    for name in names:
        p = directory / name
        p.write_text(f"-- {name}\n", encoding="utf-8")
        paths.append(p)
    return paths


def test_list_available_returns_sql_files_sorted(tmp_path: Path) -> None:
    _make_files(
        tmp_path,
        # Order is intentionally jumbled to verify sorting.
        ["0003_three.sql", "0001_one.sql", "0002_two.sql", "README.md", "ignore.txt"],
    )

    result = list_available(tmp_path)

    assert [p.name for p in result] == ["0001_one.sql", "0002_two.sql", "0003_three.sql"]


def test_list_available_ignores_non_numeric_prefix(tmp_path: Path) -> None:
    _make_files(tmp_path, ["draft_something.sql", "0001_one.sql"])

    result = list_available(tmp_path)

    assert [p.name for p in result] == ["0001_one.sql"]


def test_pending_empty_applied_returns_all(tmp_path: Path) -> None:
    available = _make_files(tmp_path, ["0001_a.sql", "0002_b.sql"])

    result = pending(applied_names=set(), available=available)

    assert [p.name for p in result] == ["0001_a.sql", "0002_b.sql"]


def test_pending_fully_applied_returns_empty(tmp_path: Path) -> None:
    available = _make_files(tmp_path, ["0001_a.sql", "0002_b.sql"])

    result = pending(applied_names={"0001_a.sql", "0002_b.sql"}, available=available)

    assert result == []


def test_pending_partial_applied_returns_remaining(tmp_path: Path) -> None:
    available = _make_files(tmp_path, ["0001_a.sql", "0002_b.sql", "0003_c.sql"])

    result = pending(applied_names={"0001_a.sql"}, available=available)

    assert [p.name for p in result] == ["0002_b.sql", "0003_c.sql"]


def test_pending_ignores_unknown_applied_names(tmp_path: Path) -> None:
    """An applied name with no matching file on disk is fine — perhaps the
    file was renamed and replaced with a new migration. `pending` reports
    based on what's on disk, not what's in the table."""
    available = _make_files(tmp_path, ["0001_a.sql"])

    result = pending(applied_names={"0001_a.sql", "0999_phantom.sql"}, available=available)

    assert result == []


def test_pending_preserves_lexical_order(tmp_path: Path) -> None:
    available = _make_files(tmp_path, ["0001_a.sql", "0002_b.sql", "0010_j.sql"])

    result = pending(applied_names=set(), available=available)

    assert [p.name for p in result] == ["0001_a.sql", "0002_b.sql", "0010_j.sql"]


def test_real_0001_is_discoverable_by_runner() -> None:
    """The real migrations/ directory MUST contain 0001 and be discoverable."""
    repo_root = Path(__file__).resolve().parents[2]
    migrations_dir = repo_root / "migrations"

    files = list_available(migrations_dir)

    assert any(f.name == "0001_init_vector_store.sql" for f in files), (
        f"0001 not discovered; got {[f.name for f in files]!r}"
    )


def test_0001_sql_declares_pinned_vector_dim() -> None:
    """Belt-and-braces: the shipped SQL MUST hard-pin the vector to 768.

    If a future contributor accidentally parameterizes this (e.g., to
    Jinja-template it from env), the test fails — and the constitution
    Art IV.3 + Art II + spec FR-005 link breaks.
    """
    repo_root = Path(__file__).resolve().parents[2]
    sql = (repo_root / "migrations" / "0001_init_vector_store.sql").read_text(encoding="utf-8")

    assert "vector(768)" in sql, "0001 MUST declare embedding as vector(768)"


@pytest.mark.parametrize(
    "must_appear",
    [
        "CREATE EXTENSION IF NOT EXISTS vector",
        "CREATE TABLE source_document",
        "CREATE TABLE chunk",
        "REFERENCES source_document(id) ON DELETE CASCADE",
        "page_number         INTEGER      NOT NULL",
        "char_offset_start",
        "char_offset_end",
        "raw_text            TEXT         NOT NULL",
        "UNIQUE (source_document_id, page_number, char_offset_start, char_offset_end)",
        "CREATE INDEX idx_chunk_source",
    ],
)
def test_0001_carries_required_clauses(must_appear: str) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    sql = (repo_root / "migrations" / "0001_init_vector_store.sql").read_text(encoding="utf-8")
    assert must_appear in sql, f"clause missing from 0001: {must_appear!r}"
