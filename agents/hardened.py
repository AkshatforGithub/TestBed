"""Hardened: same agent, but tools are wrapped (timeout/retry/validate/idempotency)."""
from langgraph.prebuilt import create_react_agent

from agents.common import POLICY_PROMPT, RELIABILITY_PROMPT, harden
from testbed.llm import get_llm


def build_hardened(tools, model: str | None = None):
    return create_react_agent(
        get_llm(model=model),
        [harden(t) for t in tools],
        prompt=POLICY_PROMPT + "\n\n" + RELIABILITY_PROMPT,
    )