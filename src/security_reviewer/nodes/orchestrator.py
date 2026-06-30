"""The ORCHESTRATOR node — triage, not detection.

The orchestrator reads the whole file once and decides *which* specialist
reviews are worth running. It returns an :class:`OrchestratorPlan` (validated
structured output), which the graph then fans out into parallel reviewer
subagents.

This module exposes a *factory* (``make_orchestrator_node``) rather than a bare
function. The factory closes over the ``llm`` so that:
  - production code passes the real ChatAnthropic model, and
  - tests pass a fake model that returns canned plans (no API calls).

This dependency-injection pattern is the single most useful thing for keeping an
LLM graph testable.

Docs: structured output — https://python.langchain.com/docs/how_to/structured_output/
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from ..prompts import ORCHESTRATOR_SYSTEM
from ..schemas import OrchestratorPlan, ReviewTask
from ..state import ReviewState


def make_orchestrator_node(llm):
    """Return an orchestrator node bound to ``llm``."""

    # `.with_structured_output(Schema)` returns a runnable whose `.invoke()`
    # yields a validated `OrchestratorPlan` instance instead of raw text.
    planner = llm.with_structured_output(OrchestratorPlan)

    def orchestrator_node(state: ReviewState) -> dict:
        messages = [
            SystemMessage(content=ORCHESTRATOR_SYSTEM),
            HumanMessage(
                content=(
                    f"Language: {state.get('language', 'unknown')}\n\n"
                    f"Code under review:\n```\n{state['code']}\n```"
                )
            ),
        ]
        plan: OrchestratorPlan = planner.invoke(messages)

        tasks = list(plan.tasks)
        # Safety net: if the model returns no tasks, do one broad sweep rather
        # than letting the graph end with nothing reviewed. (An empty fan-out
        # would skip the reviewer stage entirely — see graph.assign_reviewers.)
        if not tasks:
            tasks = [
                ReviewTask(
                    category="input_validation",
                    focus="the whole file",
                    rationale="Orchestrator returned no targeted tasks; running a broad sweep.",
                )
            ]

        return {"summary": plan.summary, "plan": tasks}

    return orchestrator_node
