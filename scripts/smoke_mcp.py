"""Smoke test with NO LLM: start the MCP server, call tools raw vs hardened under faults.

  python scripts/smoke_mcp.py --rate 0.5 --seed 1
"""
import argparse
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_mcp_adapters.tools import load_mcp_tools  # noqa: E402

from agents.common import harden, make_client  # noqa: E402
from testbed import config  # noqa: E402


async def main(args):
    fd, state = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    client = make_client({
        "FAULT_RATE": str(args.rate), "FAULT_MODES": args.modes, "FAULT_SEED": str(args.seed),
        "FAULT_HANG_SECONDS": str(args.hang), "STATE_PATH": state, "DB_PATH": str(config.DB_PATH),
    })
    async with client.session("orders") as session:
        tools = {t.name: t for t in await load_mcp_tools(session)}
        print("tools:", sorted(tools))

        print("\n-- raw lookup_order x5 --")
        for i in range(5):
            try:
                out = await asyncio.wait_for(tools["lookup_order"].ainvoke({"order_id": "A100"}), args.hang + 2)
                print(i, "->", str(out)[:80])
            except Exception as e:  # noqa: BLE001
                print(i, "-> EXC", type(e).__name__, str(e)[:60])

        print("\n-- hardened lookup_order x5 --")
        safe_lookup = harden(tools["lookup_order"], retries=4, timeout=args.hang / 2, backoff=0.1)
        for i in range(5):
            print(i, "->", (await safe_lookup.ainvoke({"order_id": "A100"}))[:80])

        print("\n-- hardened issue_refund (A103, 18.5) --")
        safe_refund = harden(tools["issue_refund"], retries=4, timeout=args.hang / 2, backoff=0.1)
        print(await safe_refund.ainvoke({"order_id": "A103", "amount": 18.5}))

    print("\nserver state:", json.loads(Path(state).read_text()))
    os.unlink(state)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rate", type=float, default=0.0)
    ap.add_argument("--modes", default="error,timeout,malformed,post_commit")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--hang", type=float, default=2.0)
    asyncio.run(main(ap.parse_args()))
