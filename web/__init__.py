"""Web visualization layer for the LangGraph security reviewer.

- ``github_fetch`` : turn a repo/PR URL into a list of source files.
- ``heuristics``   : fast regex pre-scan (powers offline SCHEMATIC mode).
- ``review_service``: run the graph (or heuristics) and emit a stream of events.
- ``server``       : FastAPI app serving the UI and an SSE endpoint.
"""
