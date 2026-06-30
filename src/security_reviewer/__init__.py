"""A LangGraph-based security code-review agent, built for learning.

The package exposes one main entry point, :func:`build_graph`, which wires the
four-stage pipeline:

    read  ->  orchestrator  ->  reviewer (xN, in parallel)  ->  reporter

See ``graph.py`` for how the stages connect, and the ``nodes/`` package for what
each stage does. The README walks through the whole thing with documentation links.
"""

from .graph import build_graph

__all__ = ["build_graph"]
