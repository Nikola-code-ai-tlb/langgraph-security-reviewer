"""Graph state — the shared memory that flows through the pipeline.

LangGraph passes a single state object from node to node. Each node returns a
*partial* update (a dict of just the keys it changed); LangGraph merges it in.

The one subtlety is ``findings``. Many reviewer subagents run **in parallel** and
all write to ``findings`` in the same super-step. Without help, those concurrent
writes would clobber each other. Annotating the key with a *reducer*
(``operator.add``, i.e. list concatenation) tells LangGraph to *append* every
worker's contribution instead of overwriting. This is the canonical map-reduce
pattern.

Docs:
  - State & reducers: https://docs.langchain.com/oss/python/langgraph/use-graph-api#state
  - Map-reduce / Send: https://docs.langchain.com/oss/python/langgraph/use-graph-api#map-reduce
"""

from __future__ import annotations

import operator
from typing import Annotated

from typing_extensions import TypedDict

from .schemas import Finding, ReviewTask


class ReviewState(TypedDict, total=False):
    """The overall graph state, shared by every node.

    ``total=False`` means every key is optional — nodes fill keys in as the
    pipeline progresses (read sets ``code``, orchestrator sets ``plan``, etc.).
    """

    # --- inputs (set by the caller) ---
    file_path: str   # path to the file under review (optional if `code` is given directly)
    code: str        # the source code itself

    # --- set by the reader node ---
    language: str    # detected language, e.g. "python"

    # --- set by the orchestrator node ---
    summary: str             # the orchestrator's one-line risk read
    plan: list[ReviewTask]   # the review tasks dispatched to subagents

    # --- written by reviewer subagents, in parallel ---
    # The reducer concatenates each subagent's findings instead of overwriting.
    findings: Annotated[list[Finding], operator.add]

    # --- set by the reporter node ---
    report: str      # the final, human-readable Markdown report


class ReviewerState(TypedDict):
    """The private state handed to a single reviewer subagent via ``Send``.

    A worker doesn't need the whole ReviewState — just the code and its one task.
    It still writes back to the shared ``findings`` key (with the same reducer),
    which is how its output rejoins the main graph.
    """

    code: str
    language: str
    task: ReviewTask
    findings: Annotated[list[Finding], operator.add]
