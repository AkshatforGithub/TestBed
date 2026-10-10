"""Shared prompts, MCP client factory and the tool-hardening wrapper."""
import asyncio
import json
import sys

from langchain_core.tools import StructuredTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from testbed import config

POLICY_PROMPT = """You are a customer-support agent for an online store. Tools: lookup_order, issue_refund.
Policy:
- Only delivered orders can be refunded. Never refund orders that are shipped, processing or cancelled.
- A refund may never exceed the order total.
- Always call lookup_order before issue_refund and base decisions on its result.
- Issue each requested refund exactly once.
- If a request cannot be done under policy, explain why and do not call issue_refund."""

RELIABILITY_PROMPT = """Reliability rules:
- Tool results may be errors or malformed. If a call fails, retry it or re-check with lookup_order; never guess an order's data.
- issue_refund is idempotent, so retrying a failed refund call is safe.
- If you still cannot finish, say so plainly instead of claiming success."""


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


def as_text(out) -> str:
    if isinstance(out, str):
        return out
    if isinstance(out, list):  # MCP content blocks
        return "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in out)
    return json.dumps(out)


def harden(tool, retries: int | None = None, timeout: float | None = None, backoff: float = 0.5):
    """Wrap a tool with: per-call timeout, retries with backoff, output validation,
    an idempotency key for refunds, and a clean structured error when retries run out."""
    retries = retries or config.TOOL_RETRIES
    timeout = timeout or config.TOOL_TIMEOUT_SECONDS

    async def run(**kwargs):
        if tool.name == "issue_refund" and "order_id" in kwargs and "amount" in kwargs:
            kwargs["idempotency_key"] = f"{kwargs['order_id']}:{float(kwargs['amount']):.2f}"
        last = None
        for attempt in range(retries):
            try:
                out = await asyncio.wait_for(tool.ainvoke(kwargs), timeout)
                text = as_text(out)
                json.loads(text)  # reject garbled output
                return text
            except Exception as e:  # noqa: BLE001 - any failure is retryable here
                last = e
                if attempt < retries - 1:
                    await asyncio.sleep(backoff * 2**attempt)
        return json.dumps({"error": f"tool unavailable after {retries} attempts: {type(last).__name__}"})

    return StructuredTool(
        name=tool.name,
        description=tool.description,
        args_schema=tool.args_schema,
        coroutine=run,
    )
