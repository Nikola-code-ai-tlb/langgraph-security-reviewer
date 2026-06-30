"""Command-line entry point.

Usage:
    python run_review.py examples/vulnerable_app.py
    python run_review.py path/to/your/file.py --out report.md

This builds the real graph (which talks to the Claude API, so you need
ANTHROPIC_API_KEY set), runs it over the given file, and prints the Markdown
report.
"""

from __future__ import annotations

import argparse
import sys

# Make `src/` importable when running this script from the repo root.
sys.path.insert(0, "src")

from security_reviewer import build_graph  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="LangGraph security code reviewer.")
    parser.add_argument("file", help="Path to the source file to review.")
    parser.add_argument("--out", help="Optional path to write the Markdown report to.")
    args = parser.parse_args()

    graph = build_graph()

    # `invoke` runs the whole pipeline and returns the final merged state.
    final_state = graph.invoke({"file_path": args.file})
    report = final_state["report"]

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(report)
        print(f"Report written to {args.out}")
    else:
        print(report)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
