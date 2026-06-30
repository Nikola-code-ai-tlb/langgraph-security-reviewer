"""Pydantic schemas — the typed contracts between the model and our code.

We never parse free-form model text. Instead we ask the model for *structured
output*: we hand it a Pydantic class and LangChain forces the response to match
it (via Anthropic tool-calling under the hood). Every field below is something
the model fills in, validated before it reaches our graph.

Docs:
  - Structured output: https://python.langchain.com/docs/concepts/structured_outputs/
  - .with_structured_output(): https://python.langchain.com/docs/how_to/structured_output/
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

# Ordered worst-to-best. The reporter uses this exact ordering to sort findings.
Severity = Literal["critical", "high", "medium", "low", "info"]

# The security categories the orchestrator may dispatch a reviewer for. Keeping
# this a closed set (a Literal) means the model can't invent a category we don't
# have a prompt for, and the value flows straight into the reviewer's focus.
Category = Literal[
    "injection",          # SQLi, command injection, template injection, eval
    "secrets",            # hardcoded credentials, tokens, keys
    "authentication",     # auth/session/access-control flaws
    "cryptography",       # weak hashing, bad randomness, misuse of crypto
    "deserialization",    # pickle/yaml.load and other unsafe deserialization
    "input_validation",   # path traversal, SSRF, missing validation
    "dependency",         # known-vulnerable or risky dependency usage
    "misconfiguration",   # debug mode, permissive CORS, insecure defaults
]


class ReviewTask(BaseModel):
    """One unit of work the orchestrator hands to a reviewer subagent."""

    category: Category = Field(description="The vulnerability class to focus on.")
    focus: str = Field(
        description="What specifically to look at, e.g. 'the build_query() string formatting'."
    )
    rationale: str = Field(
        description="Why the orchestrator flagged this area as worth a closer look."
    )


class OrchestratorPlan(BaseModel):
    """The orchestrator's output: which reviews to run, in parallel."""

    summary: str = Field(description="One-sentence read on the code's risk surface.")
    tasks: list[ReviewTask] = Field(
        description="The review tasks to dispatch. Only include genuinely relevant categories."
    )


class Finding(BaseModel):
    """A single vulnerability a reviewer subagent identified, with a fix."""

    category: Category = Field(description="Vulnerability class this finding belongs to.")
    severity: Severity = Field(description="Impact/likelihood rating.")
    title: str = Field(description="Short, specific headline, e.g. 'SQL injection in get_user()'.")
    line: Optional[int] = Field(
        default=None, description="1-indexed line number the issue anchors to, if known."
    )
    explanation: str = Field(description="What is wrong and why it is exploitable.")
    suggested_fix: str = Field(
        description="A concrete remediation, including a corrected code snippet where useful."
    )
    confidence: Literal["high", "medium", "low"] = Field(
        description="How sure the reviewer is that this is a real issue."
    )


class ReviewerOutput(BaseModel):
    """A reviewer subagent's output: zero or more findings for its category."""

    findings: list[Finding] = Field(
        default_factory=list,
        description="Findings for this reviewer's assigned category. Empty if the code is clean.",
    )
