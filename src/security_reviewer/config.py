"""Configuration and the LLM factory.

We keep all "how do we talk to the model" details in one place so the rest of the
code never imports ``langchain_anthropic`` directly. That makes the nodes easy to
test: the test suite injects a fake model instead of calling this factory.

Docs:
  - ChatAnthropic: https://python.langchain.com/docs/integrations/chat/anthropic/
  - Model IDs / pricing: https://docs.claude.com/en/docs/about-claude/models/overview
"""

from __future__ import annotations

import os

# Load a local .env (if present) so ANTHROPIC_API_KEY is available during dev.
# This is a no-op in production where the env var is set by the environment.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is optional at runtime
    pass


# Default to Claude Opus 4.8 — the most capable model for nuanced security
# reasoning. Override per-environment with SECURITY_REVIEWER_MODEL.
DEFAULT_MODEL = os.environ.get("SECURITY_REVIEWER_MODEL", "claude-opus-4-8")


def get_llm(model: str | None = None, **kwargs):
    """Create the chat model used by the orchestrator and reviewer nodes.

    Imported lazily so that importing the package (and running the offline test
    suite) never requires ``langchain_anthropic`` or an API key.
    """
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(
        model=model or DEFAULT_MODEL,
        # Generous ceiling: a reviewer may emit several findings with fixes.
        max_tokens=8000,
        # 2 minutes — security reasoning over a file can take a while.
        timeout=120,
        **kwargs,
    )
