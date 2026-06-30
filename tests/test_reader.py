"""Tests for the read node (no LLM involved)."""

from __future__ import annotations

import pytest

from security_reviewer.nodes.reader import read_node


def test_reads_inline_code_and_detects_unknown_language():
    out = read_node({"code": "print('hi')"})
    assert out["code"] == "print('hi')"
    assert out["language"] == "unknown"


def test_reads_from_file_path_and_detects_language(tmp_path):
    f = tmp_path / "snippet.py"
    f.write_text("x = 1\n", encoding="utf-8")

    out = read_node({"file_path": str(f)})
    assert out["code"] == "x = 1\n"
    assert out["language"] == "python"


def test_inline_code_takes_precedence_over_file_path(tmp_path):
    f = tmp_path / "snippet.py"
    f.write_text("from disk", encoding="utf-8")

    out = read_node({"file_path": str(f), "code": "inline"})
    assert out["code"] == "inline"
    # Language is still derived from the path extension.
    assert out["language"] == "python"


def test_errors_without_code_or_path():
    with pytest.raises(ValueError):
        read_node({})
