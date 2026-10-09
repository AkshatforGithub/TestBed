"""Baseline: prebuilt ReAct agent, raw MCP tools, policy prompt only."""
from langgraph.prebuilt import create_react_agent


from agents.common import POLICY_PROMPT
from testbed.llm import get_llm


def build_baseline(tools):
    return create_react_agent(get_llm(), tools, prompt=POLICY_PROMPT)
