"""Run agents x scenarios x tasks x seeds, grade by server state, append rows to a JSONL file.

  python -m harness.run_eval --agents baseline,hardened --scenarios clean,mixed_30 --split dev --trials 3
  python -m harness.run_eval --split test --agents baseline,hardened,graph --scenarios clean,mixed_30 --resume
"""
import argparse
import asyncio
import json
import os
import tempfile
import time
import zlib
from pathlib import Path


from langchain_core.messages import AIMessage
from langchain_mcp_adapters.tools import load_mcp_tools

from agents.baseline import build_baseline
from agents.common import make_client
from agents.hardened import build_hardened
from harness.checker import diagnose, read_refunds
from testbed import config

BUILDERS = {"baseline": build_baseline, "hardened": build_hardened}
ALL_MODES = ["error", "timeout", "malformed", "post_commit"]
SCENARIOS = {  # name -> (fault rate, fault modes)
    "clean": (0.0, ALL_MODES),
    "mixed_20": (0.2, ALL_MODES),
    "mixed_30": (0.3, ALL_MODES),
    "mixed_40": (0.4, ALL_MODES),
    "error": (0.4, ["error"]),
    "timeout": (0.4, ["timeout"]),
    "malformed": (0.4, ["malformed"]),
    "post_commit": (0.4, ["post_commit"]),
}

RETRIES = 2
BACKOFF = 20  
FALLBACK_MODEL = os.environ.get("FALLBACK_MODEL", "qwen/qwen3-32b")


def load_tasks(split: str):
    tasks = [json.loads(line) for line in config.TASKS_PATH.read_text().splitlines() if line.strip()]
    return tasks if split == "all" else [t for t in tasks if t["split"] == split]


def leaf(e: BaseException) -> BaseException:
    """Unwrap ExceptionGroup (raised by the MCP task group) down to the real error."""
    while isinstance(e, BaseExceptionGroup) and e.exceptions:
        e = e.exceptions[0]
    return e


async def _attempt(task, agent_name, scenario, seed, sem, model=None):
    rate, modes = SCENARIOS[scenario]
    async with sem:
        fd, state_path = tempfile.mkstemp(suffix=".json", prefix="testbed_")
        os.close(fd)
        env = {
            "FAULT_RATE": str(rate),
            "FAULT_MODES": ",".join(modes),
            "FAULT_SEED": str(seed),
            "FAULT_HANG_SECONDS": str(config.FAULT_HANG_SECONDS),
            "STATE_PATH": state_path,
            "DB_PATH": str(config.DB_PATH),
            "FAULT_SEED": str(zlib.crc32(f"{task['id']}|{seed}".encode())),
        }
        row = {
            "task": task["id"], "category": task["category"], "split": task["split"],
            "agent": agent_name, "scenario": scenario, "seed": seed,
            "success": False, "reason": "", "tool_calls": 0, "tokens": 0, "latency_s": 0.0,
        }
        t0 = time.time()
        try:
            client = make_client(env)
            async with client.session("orders") as session:  # one server process for the whole run
                tools = await load_mcp_tools(session)
                agent = BUILDERS[agent_name](tools, model=model)
                out = await asyncio.wait_for(
                    agent.ainvoke(
                        {"messages": [("user", task["prompt"])]},
                        config={"recursion_limit": config.RECURSION_LIMIT},
                    ),
                    timeout=config.TASK_TIMEOUT_SECONDS,
                )
            ai = [m for m in out["messages"] if isinstance(m, AIMessage)]
            row["tool_calls"] = sum(len(m.tool_calls) for m in ai)
            row["tokens"] = sum((m.usage_metadata or {}).get("total_tokens", 0) for m in ai)
            row["reason"] = diagnose(read_refunds(state_path), task["expect"])
        except Exception as e:  # noqa: BLE001 - a crash is a failed run, not a harness bug
            err = leaf(e)
            row["reason"] = f"crash:{type(err).__name__}:{str(err)[:150]}"
        row["success"] = row["reason"] == "ok"
        row["latency_s"] = round(time.time() - t0, 2)
        try:
            os.unlink(state_path)
        except OSError:
            pass
        return row


def is_rate_limit(reason: str) -> bool:
    return reason.startswith("crash:RateLimitError")


async def run_one(task, agent_name, scenario, seed, sem):
    """Retry the primary model on 429s, then fall back. Each attempt gets a fresh server and state."""
    for i in range(RETRIES + 1):
        row = await _attempt(task, agent_name, scenario, seed, sem, model=None)
        if not is_rate_limit(row["reason"]):
            row["model"] = "primary"
            return row
        if i < RETRIES:
            await asyncio.sleep(BACKOFF * (i + 1))  # outside the semaphore, so others keep running
    row = await _attempt(task, agent_name, scenario, seed, sem, model=FALLBACK_MODEL)
    row["model"] = f"fallback:{FALLBACK_MODEL}"
    return row


def row_key(r):
    return f"{r['task']}|{r['agent']}|{r['scenario']}|{r['seed']}"


async def main(args):
    agents = args.agents.split(",")
    scenarios = args.scenarios.split(",")
    tasks = load_tasks(args.split)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    done = set()
    if args.resume and out_path.exists():
        done = {row_key(json.loads(l)) for l in out_path.read_text().splitlines() if l.strip()}

    jobs = []
    for sc in scenarios:
        for ag in agents:
            for t in tasks:
                for seed in range(args.trials):
                    if f"{t['id']}|{ag}|{sc}|{seed}" not in done:
                        jobs.append((t, ag, sc, seed))

    sem, lock = asyncio.Semaphore(args.concurrency), asyncio.Lock()
    counter = {"n": 0}
    f = open(out_path, "a" if args.resume else "w")

    async def worker(job):
        row = await run_one(*job, sem)
        async with lock:
            counter["n"] += 1
            f.write(json.dumps(row) + "\n")
            f.flush()
            print(f"[{counter['n']}/{len(jobs)}] {row['agent']:<8} {row['scenario']:<12} {row['task']} seed={row['seed']} [{row['model']}] -> {row['reason']}")

    await asyncio.gather(*(worker(j) for j in jobs))
    f.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--agents", default="baseline,hardened")
    ap.add_argument("--scenarios", default="clean,mixed_30")
    ap.add_argument("--split", default="dev", choices=["dev", "test", "all"])
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--out", default=str(config.RESULTS_DIR / "runs.jsonl"))
    ap.add_argument("--resume", action="store_true")
    asyncio.run(main(ap.parse_args()))