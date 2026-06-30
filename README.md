# LangGraph Security Code Reviewer

A small, heavily-commented **LangGraph** agent that reviews a source file for
security vulnerabilities. Built for **learning** — every node is documented and
linked to the relevant docs, and the whole pipeline can run **offline** in tests
without an API key.

The workflow mirrors how a human security team triages code:

```
   read  →  orchestrator  →  reviewer × N (parallel)  →  reporter
```

1. **read** — load the file into the shared graph state.
2. **orchestrator** — triage: skim the code and decide *which* specialist
   reviews are worth running. Produces a list of `ReviewTask`s.
3. **reviewer** (the subagent) — one runs *per task, in parallel*. Each looks at
   the code through a single lens (injection, secrets, crypto, …) and returns
   findings, each with a concrete fix.
4. **reporter** — aggregate every reviewer's findings into one sorted Markdown
   report.

---

## Why this shape? (the concepts worth learning)

This project is really a tour of four LangGraph ideas. Read the code in this
order:

| Concept | Where | What to notice |
|---|---|---|
| **State + reducers** | [`state.py`](src/security_reviewer/state.py) | `findings` is `Annotated[list, operator.add]` so parallel writers *append* instead of clobbering. |
| **Nodes** | [`nodes/`](src/security_reviewer/nodes/) | A node is just `state -> partial update`. Two are LLM-backed, two are plain functions. |
| **Orchestrator-worker / `Send`** | [`graph.py`](src/security_reviewer/graph.py) | `assign_reviewers` returns a list of `Send("reviewer", …)` — that's the parallel fan-out. |
| **Structured output** | [`schemas.py`](src/security_reviewer/schemas.py) | We never parse free text; the model fills in validated Pydantic objects. |

Reference docs:
- LangGraph Graph API — https://docs.langchain.com/oss/python/langgraph/use-graph-api
- Map-reduce with `Send` — https://docs.langchain.com/oss/python/langgraph/use-graph-api#map-reduce
- Orchestrator-worker workflow — https://docs.langchain.com/oss/python/langgraph/workflows-agents
- Structured output (LangChain) — https://python.langchain.com/docs/how_to/structured_output/
- ChatAnthropic — https://python.langchain.com/docs/integrations/chat/anthropic/

---

## The graph, drawn

```
        START
          │
        read                 (reader.py — no LLM)
          │
     orchestrator            (orchestrator.py — LLM → OrchestratorPlan)
          │
   assign_reviewers          (graph.py — conditional edge returning Send[])
        ╱ │ ╲                 one Send per task → parallel subagents
  reviewer reviewer …        (reviewer.py — LLM → ReviewerOutput, appends findings)
        ╲ │ ╱
       reporter              (reporter.py — no LLM, deterministic Markdown)
          │
         END
```

---

## Setup

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Unix:     source .venv/bin/activate

pip install -r requirements.txt

cp .env.example .env        # then put your real ANTHROPIC_API_KEY in .env
```

The model defaults to `claude-opus-4-8`. Override with `SECURITY_REVIEWER_MODEL`.

## Run it

```bash
python run_review.py examples/vulnerable_app.py
# or write the report to a file:
python run_review.py examples/vulnerable_app.py --out report.md
```

[`examples/vulnerable_app.py`](examples/vulnerable_app.py) is a deliberately
insecure sample with one planted bug per category — a good first target.

## Test it (no API key needed)

The test suite injects a **fake model** (`tests/conftest.py`) via the same
`build_graph(llm=…)` seam the CLI uses, so the entire graph — including the
parallel fan-out — runs deterministically offline:

```bash
pip install -r requirements.txt   # for langgraph + pytest
pytest -q
```

---

## Project layout

```
run_review.py                       CLI entry point
src/security_reviewer/
  config.py                         model id + LLM factory (the test seam)
  schemas.py                        Pydantic contracts (plan, task, finding)
  state.py                          graph state + the operator.add reducer
  prompts.py                        system prompts for the LLM nodes
  graph.py                          wires nodes together; the Send fan-out
  nodes/
    reader.py                       load code into state
    orchestrator.py                 triage → ReviewTask list
    reviewer.py                     subagent: review one category, propose fix
    reporter.py                     aggregate → Markdown
examples/vulnerable_app.py          insecure sample input
tests/                              offline tests (fake model)
```

## Extending it (exercises)

- Give the **reporter** an LLM-written executive summary (it's deterministic now
  — see the note at the top of `reporter.py`).
- Add a **human-in-the-loop** approval gate before the reporter using LangGraph
  `interrupt` — https://docs.langchain.com/oss/python/langgraph/add-human-in-the-loop
- Add a **verifier** node after the reviewers that re-checks each finding to cut
  false positives, then routes low-confidence ones away.
- Support a whole directory: a `read` that fans out one `orchestrator` per file.

> ⚠️ This is a learning aid. An LLM reviewer complements but does not replace
> dedicated SAST tooling and human review.
