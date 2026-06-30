"""Tests for the orchestrator node, using the fake LLM."""

from __future__ import annotations

from security_reviewer.nodes.orchestrator import make_orchestrator_node
from security_reviewer.schemas import OrchestratorPlan, ReviewTask


def test_returns_plan_from_model(make_fake_llm):
    def responder(schema, _messages):
        assert schema is OrchestratorPlan
        return OrchestratorPlan(
            summary="risky",
            tasks=[ReviewTask(category="injection", focus="x", rationale="y")],
        )

    node = make_orchestrator_node(make_fake_llm(responder))
    out = node({"code": "code", "language": "python"})

    assert out["summary"] == "risky"
    assert len(out["plan"]) == 1
    assert out["plan"][0].category == "injection"


def test_empty_plan_falls_back_to_broad_sweep(make_fake_llm):
    def responder(_schema, _messages):
        return OrchestratorPlan(summary="clean?", tasks=[])

    node = make_orchestrator_node(make_fake_llm(responder))
    out = node({"code": "code", "language": "python"})

    # The fallback guarantees the reviewer stage is not skipped entirely.
    assert len(out["plan"]) == 1
    assert out["plan"][0].category == "input_validation"
