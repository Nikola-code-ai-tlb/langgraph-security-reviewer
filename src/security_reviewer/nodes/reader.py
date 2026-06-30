"""The READ node — the entry point of the pipeline.

This node has no LLM and no surprises: it makes sure ``state["code"]`` is
populated (reading it from ``file_path`` if needed) and detects the language so
later nodes/prompts have that context.

A "node" in LangGraph is just a function ``state -> partial_state_update``. This
one returns the keys it wants to add to the shared state; LangGraph merges them.

Docs: https://docs.langchain.com/oss/python/langgraph/use-graph-api#nodes
"""

from __future__ import annotations

from pathlib import Path

from ..state import ReviewState

# Map common file extensions to a language label used in prompts/reports.
_EXT_TO_LANG = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".java": "java",
    ".go": "go",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".sh": "bash",
}


def read_node(state: ReviewState) -> dict:
    """Load source code into state and detect its language.

    Accepts either:
      - ``code`` directly (handy for tests and ad-hoc snippets), or
      - ``file_path``, which we read from disk.
    """
    code = state.get("code")
    file_path = state.get("file_path")

    if not code:
        if not file_path:
            raise ValueError("read_node requires either 'code' or 'file_path' in state.")
        code = Path(file_path).read_text(encoding="utf-8")

    language = "unknown"
    if file_path:
        language = _EXT_TO_LANG.get(Path(file_path).suffix.lower(), "unknown")

    return {"code": code, "language": language}
