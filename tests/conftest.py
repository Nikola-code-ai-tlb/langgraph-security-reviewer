"""Shared test fixtures — most importantly, an offline fake LLM.

The whole point of the dependency-injection design (factories that take an
``llm``) is that we can run the entire graph without an API key. The fake below
implements just the two methods our nodes use:

    structured = llm.with_structured_output(SomeSchema)
    result     = structured.invoke(messages)

A test supplies a ``responder(schema, messages) -> pydantic_instance`` callable,
so it has full control over what the "model" returns for each schema.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make `src/` importable for the test session.
SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from security_reviewer.schemas import (  # noqa: E402
    Finding,
    OrchestratorPlan,
    ReviewerOutput,
    ReviewTask,
)


class _StructuredRunnable:
    """Stands in for ``llm.with_structured_output(schema)``."""

    def __init__(self, responder, schema):
        self._responder = responder
        self._schema = schema

    def invoke(self, messages):
        return self._responder(self._schema, messages)


class FakeLLM:
    """A minimal fake chat model for offline tests."""

    def __init__(self, responder):
        # responder: (schema_class, messages) -> instance of schema_class
        self._responder = responder

    def with_structured_output(self, schema, **_kwargs):
        return _StructuredRunnable(self._responder, schema)


@pytest.fixture
def make_fake_llm():
    """Factory fixture: build a FakeLLM from a responder function."""

    def _make(responder):
        return FakeLLM(responder)

    return _make


@pytest.fixture
def canned_responder():
    """A responder that returns a fixed plan and findings, keyed by schema.

    Used by the end-to-end graph test: the orchestrator gets a 2-task plan, and
    each reviewer returns one finding tagged 'injection' (the reviewer node will
    re-tag it to its own category, which the test verifies).
    """

    def responder(schema, _messages):
        if schema is OrchestratorPlan:
            return OrchestratorPlan(
                summary="Two risk areas identified.",
                tasks=[
                    ReviewTask(
                        category="injection",
                        focus="get_user() query construction",
                        rationale="String-formatted SQL.",
                    ),
                    ReviewTask(
                        category="secrets",
                        focus="module-level constants",
                        rationale="Looks like hardcoded credentials.",
                    ),
                ],
            )
        if schema is ReviewerOutput:
            return ReviewerOutput(
                findings=[
                    Finding(
                        category="injection",  # reviewer node should overwrite this
                        severity="high",
                        title="Example finding",
                        line=3,
                        explanation="Demonstration issue.",
                        suggested_fix="Use parameterized queries.",
                        confidence="high",
                    )
                ]
            )
        raise AssertionError(f"Unexpected schema requested: {schema!r}")

    return responder
