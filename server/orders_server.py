"""Fake orders backend exposed over MCP, with deliberate fault injection.

Faults (FAULT_MODES, drawn with probability FAULT_RATE per tool call):
  error        - raises before any side effect
  timeout      - hangs FAULT_HANG_SECONDS, then raises (before any side effect)
  malformed    - returns garbage text; for issue_refund the refund IS committed
  post_commit  - issue_refund only: commits the refund, THEN raises (the double-refund trap)

Runs as a stdio subprocess; it must never print to stdout.
"""
import asyncio
import json
import os
import random
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("orders-flaky")

RATE = float(os.getenv("FAULT_RATE", "0"))
MODES = [m for m in os.getenv("FAULT_MODES", "error,timeout,malformed,post_commit").split(",") if m]
HANG = float(os.getenv("FAULT_HANG_SECONDS", "20"))
rng = random.Random(int(os.getenv("FAULT_SEED", "0")))
STATE_PATH = Path(os.getenv("STATE_PATH", "/tmp/testbed_state.json"))
DB_PATH = Path(os.getenv("DB_PATH", Path(__file__).resolve().parent.parent / "data" / "db.json"))
DB = json.loads(DB_PATH.read_text())

GARBAGE = "<<<garbled response>>>"
refunds: list[dict] = []
seen_keys: set[str] = set()


def save() -> None:
    STATE_PATH.write_text(json.dumps({"refunds": refunds}))


def draw_fault():
    if RATE > 0 and MODES and rng.random() < RATE:
        return rng.choice(MODES)
    return None


async def apply_fault(fault):
    """error/timeout raise; malformed returns garbage; anything else is a no-op."""
    if fault == "error":
        raise RuntimeError("503 upstream unavailable")
    if fault == "timeout":
        await asyncio.sleep(HANG)
        raise TimeoutError("upstream timed out")
    if fault == "malformed":
        return GARBAGE
    return None


@mcp.tool()
async def lookup_order(order_id: str) -> str:
    """Look up an order. Returns JSON with customer, total and status."""
    fault = draw_fault()
    if fault == "post_commit":  
        fault = None
    bad = await apply_fault(fault)
    if bad:
        return bad
    order = DB.get(order_id)
    return json.dumps({"order_id": order_id, **order} if order else {"error": "order not found"})


@mcp.tool()
async def issue_refund(order_id: str, amount: float, idempotency_key: str = "") -> str:
    """Refund `amount` on an order. Pass an idempotency_key so retries are safe."""
    order = DB.get(order_id)
    if order is None:
        return json.dumps({"error": "order not found"})
    if amount <= 0:
        return json.dumps({"error": "amount must be positive"})
    if amount > order["total"]:
        return json.dumps({"error": "refund exceeds order total"})
    if idempotency_key and idempotency_key in seen_keys:
        return json.dumps({"status": "already_refunded", "order_id": order_id, "amount": amount})

    fault = draw_fault()
    if fault in ("error", "timeout"):
        await apply_fault(fault)  # raises before any side effect

    refunds.append({"order_id": order_id, "amount": amount})  # commit
    if idempotency_key:
        seen_keys.add(idempotency_key)
    save()

    if fault == "malformed":
        return GARBAGE
    if fault == "post_commit":
        raise RuntimeError("502 bad gateway (after commit)")
    return json.dumps({"status": "refunded", "order_id": order_id, "amount": amount})


if __name__ == "__main__":
    save()
    mcp.run(transport="stdio")
