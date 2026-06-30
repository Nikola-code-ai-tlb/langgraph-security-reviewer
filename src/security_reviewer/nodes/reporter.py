"""The REPORTER node — aggregate findings into a Markdown report.

This stage is deliberately *deterministic* (no LLM). By the time we get here the
hard work is done; the reporter just sorts, groups, and renders. Keeping it free
of the model makes the output stable and the node trivially unit-testable.

(If you wanted an LLM-written executive summary, this is the natural place to add
one — call the model on ``state["findings"]`` and prepend its prose. We keep it
rule-based here so tests don't need a model.)
"""

from __future__ import annotations

from ..schemas import Finding
from ..state import ReviewState

# Worst-first ordering, matching the Severity Literal in schemas.py.
_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def _sort_key(finding: Finding):
    """Sort by severity (worst first), then by line number for stable grouping."""
    return (_SEVERITY_ORDER.get(finding.severity, 99), finding.line or 0)


def report_node(state: ReviewState) -> dict:
    """Render all findings into a single Markdown document."""
    findings = sorted(state.get("findings", []), key=_sort_key)

    lines: list[str] = ["# Security Review Report", ""]

    target = state.get("file_path") or "(inline snippet)"
    lines.append(f"**Target:** `{target}`  ")
    lines.append(f"**Language:** {state.get('language', 'unknown')}  ")
    if state.get("summary"):
        lines.append(f"**Orchestrator triage:** {state['summary']}  ")
    lines.append("")

    # Severity tally, so a reader sees the shape of the risk at a glance.
    counts = {sev: 0 for sev in _SEVERITY_ORDER}
    for finding in findings:
        counts[finding.severity] = counts.get(finding.severity, 0) + 1
    tally = ", ".join(f"{counts[sev]} {sev}" for sev in _SEVERITY_ORDER)
    lines.append(f"**Findings:** {len(findings)} total ({tally})")
    lines.append("")

    if not findings:
        lines.append("No issues were identified. 🎉")
        return {"report": "\n".join(lines)}

    lines.append("---")
    lines.append("")

    for i, finding in enumerate(findings, start=1):
        location = f" (line {finding.line})" if finding.line else ""
        lines.append(
            f"## {i}. [{finding.severity.upper()}] {finding.title}{location}"
        )
        lines.append("")
        lines.append(
            f"- **Category:** {finding.category}  "
        )
        lines.append(f"- **Confidence:** {finding.confidence}")
        lines.append("")
        lines.append(f"**What's wrong:** {finding.explanation}")
        lines.append("")
        lines.append("**Suggested fix:**")
        lines.append("")
        lines.append(finding.suggested_fix)
        lines.append("")

    return {"report": "\n".join(lines)}
