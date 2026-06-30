"""Tests for the reporter node (deterministic, no LLM)."""

from __future__ import annotations

from security_reviewer.nodes.reporter import report_node
from security_reviewer.schemas import Finding


def _finding(severity, title, line=None, category="injection"):
    return Finding(
        category=category,
        severity=severity,
        title=title,
        line=line,
        explanation="why",
        suggested_fix="fix",
        confidence="high",
    )


def test_clean_report_when_no_findings():
    out = report_node({"file_path": "a.py", "language": "python", "findings": []})
    assert "No issues were identified" in out["report"]
    assert "0 critical" in out["report"]


def test_findings_sorted_worst_first():
    findings = [
        _finding("low", "Low one"),
        _finding("critical", "Critical one"),
        _finding("medium", "Medium one"),
    ]
    out = report_node({"file_path": "a.py", "language": "python", "findings": findings})
    report = out["report"]

    # Critical must appear before medium, which appears before low.
    assert report.index("Critical one") < report.index("Medium one") < report.index("Low one")


def test_report_includes_counts_and_fix_text():
    findings = [_finding("high", "H", line=12)]
    out = report_node({"file_path": "a.py", "language": "python", "findings": findings})
    report = out["report"]

    assert "1 total" in report
    assert "1 high" in report
    assert "line 12" in report
    assert "Suggested fix" in report


def test_handles_missing_optional_state_keys():
    # No file_path / summary in state — reporter should still render.
    out = report_node({"findings": [_finding("info", "Info one")]})
    assert "Security Review Report" in out["report"]
    assert "(inline snippet)" in out["report"]
