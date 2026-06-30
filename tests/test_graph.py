"""End-to-end test: the whole graph, offline, via the fake LLM.

This is the test that proves the wiring works — read -> orchestrator -> parallel
reviewers -> reporter — including the Send fan-out and the reducer fan-in.
"""

from __future__ import annotations

from security_reviewer.graph import build_graph


def test_full_pipeline_runs_offline(make_fake_llm, canned_responder):
    graph = build_graph(llm=make_fake_llm(canned_responder))

    final_state = graph.invoke({"code": "SELECT * FROM users WHERE x = '%s'"})

    # The orchestrator produced a 2-task plan...
    assert len(final_state["plan"]) == 2

    # ...so two reviewers ran in parallel, each returning one finding. The
    # reducer (operator.add) concatenated them into a single list.
    assert len(final_state["findings"]) == 2

    # One reviewer was assigned 'injection', the other 'secrets'; the reviewer
    # node re-tagged its finding to its own category. So both categories appear.
    categories = {f.category for f in final_state["findings"]}
    assert categories == {"injection", "secrets"}

    # The reporter rendered a Markdown report mentioning both findings.
    report = final_state["report"]
    assert "Security Review Report" in report
    assert "2 total" in report


def test_pipeline_reads_from_file(tmp_path, make_fake_llm, canned_responder):
    f = tmp_path / "target.py"
    f.write_text("password = 'abc'\n", encoding="utf-8")

    graph = build_graph(llm=make_fake_llm(canned_responder))
    final_state = graph.invoke({"file_path": str(f)})

    assert final_state["language"] == "python"
    assert "target.py" in final_state["report"]
