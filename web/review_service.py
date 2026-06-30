"""Run a review and emit a stream of UI events.

This is the bridge between the LangGraph pipeline and the browser. It yields
plain dicts; ``server.py`` serializes each as a Server-Sent Event. The event
vocabulary mirrors the pipeline so the frontend can light up nodes in real time:

    status      — human-readable progress line
    target      — what we're reviewing (repo/PR label)
    files       — the list of fetched files
    file_start  — begin reviewing one file
    node        — a pipeline node changed state (read/orchestrator/reporter)
    plan        — orchestrator's triage result (tasks -> reviewer nodes)
    reviewer    — a reviewer subagent finished (with its findings)
    file_done   — finished one file
    complete    — whole run finished (aggregate report + totals)
    error       — something went wrong

Two backends produce these events:
  - LIVE mode (ANTHROPIC_API_KEY present): the real LangGraph, streamed via
    ``graph.stream(..., stream_mode="updates")``.
  - SCHEMATIC mode (no key): the regex heuristics, paced with small sleeps so the
    visualization still plays. Findings are real, derived from the fetched code.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Iterator

# Make `src/` importable so we can reuse the graph package.
_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from . import heuristics
from .github_fetch import SourceFile, fetch_files, parse_target

Event = dict


def current_mode() -> str:
    """LIVE when an Anthropic key is configured, else SCHEMATIC."""
    return "live" if os.environ.get("ANTHROPIC_API_KEY") else "schematic"


def iter_review_events(url: str) -> Iterator[Event]:
    """Drive a full review and yield UI events."""
    mode = current_mode()
    try:
        yield {"type": "status", "message": "Parsing target..."}
        target = parse_target(url)
        yield {
            "type": "target",
            "kind": target.kind,
            "label": target.label,
            "url": target.url,
            "mode": mode,
        }

        yield {"type": "status", "message": f"Fetching source from {target.label}..."}
        files = fetch_files(target)
        yield {
            "type": "files",
            "files": [{"path": f.path, "lines": f.lines, "language": f.language} for f in files],
        }

        all_findings: list[dict] = []
        runner = _run_live if mode == "live" else _run_schematic

        for f in files:
            yield {"type": "file_start", "path": f.path, "language": f.language, "lines": f.lines}
            file_findings: list[dict] = []
            for event in runner(f):
                if event.get("type") == "reviewer":
                    file_findings.extend(event.get("findings", []))
                yield event
            for finding in file_findings:
                finding["file"] = f.path
            all_findings.extend(file_findings)
            yield {"type": "file_done", "path": f.path, "count": len(file_findings)}

        yield {
            "type": "complete",
            "report": _render_report(target, all_findings),
            "totals": _totals(all_findings),
            "findings_count": len(all_findings),
        }
    except Exception as exc:  # surface any failure to the UI rather than hanging
        yield {"type": "error", "message": f"{type(exc).__name__}: {exc}"}


# --------------------------------------------------------------------------- #
# LIVE backend — the real LangGraph
# --------------------------------------------------------------------------- #
def _run_live(f: SourceFile) -> Iterator[Event]:
    from security_reviewer.graph import build_graph

    graph = build_graph()
    yield {"type": "node", "node": "read", "status": "active"}

    for chunk in graph.stream(
        {"code": f.content, "file_path": f.path}, stream_mode="updates"
    ):
        for node, update in chunk.items():
            if node == "read":
                yield {"type": "node", "node": "read", "status": "done"}
                yield {"type": "node", "node": "orchestrator", "status": "active"}
            elif node == "orchestrator":
                tasks = [
                    {"category": t.category, "focus": t.focus}
                    for t in update.get("plan", [])
                ]
                yield {"type": "node", "node": "orchestrator", "status": "done"}
                yield {"type": "plan", "summary": update.get("summary", ""), "tasks": tasks}
            elif node == "reviewer":
                findings = [_finding_dict(x) for x in update.get("findings", [])]
                category = findings[0]["category"] if findings else None
                yield {"type": "reviewer", "category": category, "findings": findings}
            elif node == "reporter":
                yield {"type": "node", "node": "reporter", "status": "done"}


def _finding_dict(finding) -> dict:
    # `finding` is a Pydantic model from the graph.
    data = finding.model_dump() if hasattr(finding, "model_dump") else dict(finding)
    return data


# --------------------------------------------------------------------------- #
# SCHEMATIC backend — regex heuristics, paced for the animation
# --------------------------------------------------------------------------- #
def _run_schematic(f: SourceFile) -> Iterator[Event]:
    yield {"type": "node", "node": "read", "status": "active"}
    time.sleep(0.25)
    yield {"type": "node", "node": "read", "status": "done"}

    yield {"type": "node", "node": "orchestrator", "status": "active"}
    time.sleep(0.45)
    findings = heuristics.scan(f.content)

    # Group findings by category -> one reviewer task per category present.
    by_category: dict[str, list[dict]] = {}
    for finding in findings:
        by_category.setdefault(finding["category"], []).append(finding)

    if not by_category:
        # Nothing matched — still show one reviewer doing a clean sweep.
        by_category = {"input_validation": []}

    tasks = [{"category": c, "focus": _focus_for(c)} for c in by_category]
    yield {"type": "node", "node": "orchestrator", "status": "done"}
    yield {"type": "plan", "summary": _summary_for(f, findings), "tasks": tasks}

    for category, items in by_category.items():
        time.sleep(0.4)
        yield {"type": "reviewer", "category": category, "findings": items}

    time.sleep(0.2)
    yield {"type": "node", "node": "reporter", "status": "done"}


def _focus_for(category: str) -> str:
    return {
        "injection": "string-built commands and queries",
        "secrets": "module-level constants and literals",
        "cryptography": "hashing and randomness",
        "deserialization": "pickle/yaml load sites",
        "misconfiguration": "framework and TLS settings",
        "input_validation": "external input handling",
    }.get(category, "the whole file")


def _summary_for(f: SourceFile, findings: list[dict]) -> str:
    if not findings:
        return f"No obvious risk patterns in {f.path}."
    return f"{len(findings)} risk pattern(s) detected across {len({x['category'] for x in findings})} categories."


# --------------------------------------------------------------------------- #
# Report rendering (shared)
# --------------------------------------------------------------------------- #
_SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def _totals(findings: list[dict]) -> dict:
    totals = {sev: 0 for sev in _SEV_ORDER}
    for finding in findings:
        totals[finding["severity"]] = totals.get(finding["severity"], 0) + 1
    return totals


def _render_report(target, findings: list[dict]) -> str:
    findings = sorted(findings, key=lambda x: (_SEV_ORDER.get(x["severity"], 9), x.get("file", ""), x.get("line") or 0))
    out = ["# Security Review Report", "", f"**Target:** {target.label}  ",
           f"**Findings:** {len(findings)} total", ""]
    if not findings:
        out.append("No issues were identified.")
        return "\n".join(out)
    out.append("---")
    for i, finding in enumerate(findings, start=1):
        loc = f"{finding.get('file', '?')}:{finding.get('line', '?')}"
        out += [
            "", f"## {i}. [{finding['severity'].upper()}] {finding['title']}",
            f"`{loc}` — category: {finding['category']} — confidence: {finding.get('confidence', 'n/a')}",
            "", f"**What's wrong:** {finding['explanation']}",
            "", f"**Fix:** {finding['suggested_fix']}",
        ]
    return "\n".join(out)
