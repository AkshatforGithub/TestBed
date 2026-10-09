"""Shared prompts and MCP client factory."""
import sys

from langchain_mcp_adapters.client import MultiServerMCPClient

from testbed import config

POLICY_PROMPT = """You are a customer-support agent for an online store. Tools: lookup_order, issue_refund.
Policy:
- Only delivered orders can be refunded. Never refund orders that are shipped, processing or cancelled.
- A refund may never exceed the order total.
- Always call lookup_order before issue_refund and base decisions on its result.
- Issue each requested refund exactly once.
- If a request cannot be done under policy, explain why and do not call issue_refund."""

def make_client(env: dict[str, str]) -> MultiServerMCPClient:
    """One stdio MCP server process per client. Use client.session('orders') to keep it alive."""
    return MultiServerMCPClient(
        {
            "orders": {
                "command": sys.executable,
                "args": [str(config.SERVER_PATH)],
                "transport": "stdio",
                "env": env,
            }
        }
    )
