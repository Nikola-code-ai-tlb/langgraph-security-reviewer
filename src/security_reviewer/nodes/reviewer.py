"""The REVIEWER node — the specialist subagent.

One instance of this node runs per task the orchestrator produced, and they all
run **concurrently** (LangGraph schedules them in the same super-step). Each
instance receives a private :class:`ReviewerState` containing the code and its
single assigned task, looks at the code through that one lens, and returns
findings (with fixes).

Because the node writes to the shared ``findings`` key — which has an
``operator.add`` reducer (see ``state.py``) — every subagent's findings are
appended together rather than overwriting one another.

Docs: parallel workers via Send —
  https://docs.langchain.com/oss/python/langgraph/workflows-agents#orchestrator-worker
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from ..prompts import REVIEWER_SYSTEM, reviewer_task_prompt
from ..schemas import ReviewerOutput
from ..state import ReviewerState


def make_reviewer_node(llm):
    """Return a reviewer subagent node bound to ``llm``."""

    auditor = llm.with_structured_output(ReviewerOutput)

    def reviewer_node(state: ReviewerState) -> dict:
        task = state["task"]
        messages = [
            SystemMessage(content=REVIEWER_SYSTEM),
            HumanMessage(
                content=(
                    f"{reviewer_task_prompt(task)}\n"
                    f"Language: {state.get('language', 'unknown')}\n\n"
                    f"Code under review:\n```\n{state['code']}\n```"
                )
            ),
        ]
        output: ReviewerOutput = auditor.invoke(messages)

        # Pin every finding to this subagent's assigned category. The model is
        # asked to stay in its lane, but enforcing it here keeps the report's
        # grouping trustworthy even if the model drifts.
        for finding in output.findings:
            finding.category = task.category

        # Returning a list under the reducer-annotated key appends these to the
        # findings already gathered by sibling subagents.
        return {"findings": output.findings}

    return reviewer_node
