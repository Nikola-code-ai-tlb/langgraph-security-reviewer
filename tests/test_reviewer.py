"""Tests for the reviewer subagent node, using the fake LLM."""

from __future__ import annotations

from security_reviewer.nodes.reviewer import make_reviewer_node
from security_reviewer.schemas import Finding, ReviewerOutput, ReviewTask


def _finding(category="injection"):
    return Finding(
        category=category,
        severity="high",
        title="t",
        line=1,
        explanation="e",
        suggested_fix="f",
        confidence="high",
    )


def test_returns_findings_under_reducer_key(make_fake_llm):
    def responder(schema, _messages):
        assert schema is ReviewerOutput
        return ReviewerOutput(findings=[_finding(), _finding()])

    node = make_reviewer_node(make_fake_llm(responder))
    task = ReviewTask(category="secrets", focus="x", rationale="y")
    out = node({"code": "code", "language": "python", "task": task})

    assert "findings" in out
    assert len(out["findings"]) == 2


def test_findings_are_retagged_to_assigned_category(make_fake_llm):
    # The model returns a finding tagged 'injection', but the task is 'secrets'.
    def responder(_schema, _messages):
        return ReviewerOutput(findings=[_finding(category="injection")])

    node = make_reviewer_node(make_fake_llm(responder))
    task = ReviewTask(category="secrets", focus="x", rationale="y")
    out = node({"code": "code", "language": "python", "task": task})

    # The node enforces the assigned category so report grouping stays correct.
    assert out["findings"][0].category == "secrets"


def test_clean_code_yields_no_findings(make_fake_llm):
    def responder(_schema, _messages):
        return ReviewerOutput(findings=[])

    node = make_reviewer_node(make_fake_llm(responder))
    task = ReviewTask(category="cryptography", focus="x", rationale="y")
    out = node({"code": "code", "language": "python", "task": task})

    assert out["findings"] == []
