"""The four pipeline stages, one module each.

- reader       : load the source code into state (no LLM)
- orchestrator : triage the code into review tasks (LLM)
- reviewer     : the subagent — review one category, propose fixes (LLM)
- reporter     : aggregate findings into a Markdown report (no LLM)
"""
