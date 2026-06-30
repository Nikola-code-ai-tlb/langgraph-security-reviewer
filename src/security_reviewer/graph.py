"""Wire the four nodes into a runnable LangGraph.

The shape:

        START
          |
        read              (load code into state)
          |
     orchestrator         (triage -> list[ReviewTask])
          |
     (conditional edge: assign_reviewers)
        /  |  \\           (one Send per task -> parallel subagents)
   reviewer reviewer ...   (each reviews one category, appends findings)
        \\  |  /
       reporter           (aggregate findings -> Markdown)
          |
         END

The key construct is the **conditional edge** out of ``orchestrator``. Instead of
returning a node name, ``assign_reviewers`` returns a list of ``Send`` objects —
one per review task. LangGraph runs all of them as parallel instances of the
``reviewer`` node, each with its own private state. This is LangGraph's native
map-reduce / orchestrator-worker pattern.

Docs:
  - Graph API: https://docs.langchain.com/oss/python/langgraph/use-graph-api
  - Send / map-reduce: https://docs.langchain.com/oss/python/langgraph/use-graph-api#map-reduce
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from .nodes.orchestrator import make_orchestrator_node
from .nodes.reader import read_node
from .nodes.reporter import report_node
from .nodes.reviewer import make_reviewer_node
from .state import ReviewState


def assign_reviewers(state: ReviewState):
    """Fan out: dispatch one ``reviewer`` subagent per orchestrator task.

    Returning a list of ``Send("reviewer", worker_state)`` tells LangGraph to
    spin up that many parallel instances of the ``reviewer`` node. Each gets a
    private ``ReviewerState`` carrying just the code and its one task.
    """
    return [
        Send(
            "reviewer",
            {
                "code": state["code"],
                "language": state.get("language", "unknown"),
                "task": task,
            },
        )
        for task in state["plan"]
    ]


def build_graph(llm=None):
    """Build and compile the security-review graph.

    :param llm: a chat model with ``.with_structured_output()``. Defaults to the
        real ChatAnthropic via :func:`config.get_llm`. Tests pass a fake here so
        the whole graph runs offline.
    :returns: a compiled, invokable LangGraph.
    """
    if llm is None:
        from .config import get_llm

        llm = get_llm()

    builder = StateGraph(ReviewState)

    # Register the nodes. The two LLM nodes are built via their factories so they
    # capture `llm`; the two deterministic nodes are plain functions.
    builder.add_node("read", read_node)
    builder.add_node("orchestrator", make_orchestrator_node(llm))
    builder.add_node("reviewer", make_reviewer_node(llm))
    builder.add_node("reporter", report_node)

    # Linear spine: START -> read -> orchestrator
    builder.add_edge(START, "read")
    builder.add_edge("read", "orchestrator")

    # Fan-out: orchestrator -> (N parallel reviewers). The third arg lists the
    # possible destinations so LangGraph can validate/visualize the edge.
    builder.add_conditional_edges("orchestrator", assign_reviewers, ["reviewer"])

    # Fan-in: every reviewer flows into the single reporter. LangGraph waits for
    # all parallel reviewers to finish before running reporter (their findings
    # have all been merged via the reducer by then).
    builder.add_edge("reviewer", "reporter")
    builder.add_edge("reporter", END)

    return builder.compile()
