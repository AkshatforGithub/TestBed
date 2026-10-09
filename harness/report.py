"""Turn results/runs.jsonl into markdown tables (printed and saved to results/report.md).

  python -m harness.report --split test
"""
import argparse
import json
import math
from collections import Counter, defaultdict

from testbed import config


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - m) / d, (c + m) / d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=str(config.RESULTS_DIR / "runs.jsonl"))
    ap.add_argument("--split", default="all", choices=["dev", "test", "all"])
    ap.add_argument("--out", default=str(config.RESULTS_DIR / "report.md"))
    args = ap.parse_args()

    rows = [json.loads(l) for l in open(args.input) if l.strip()]
    if args.split != "all":
        rows = [r for r in rows if r["split"] == args.split]

    out = []
    groups = defaultdict(list)
    for r in rows:
        groups[(r["scenario"], r["agent"])].append(r)

    out += [f"### Success rate ({args.split} split)", "",
            "| scenario | agent | runs | success | 95% CI | avg latency | avg tool calls | avg tokens |",
            "|---|---|---|---|---|---|---|---|"]
    for (sc, ag), rs in sorted(groups.items()):
        n, k = len(rs), sum(r["success"] for r in rs)
        lo, hi = wilson(k, n)
        out.append(
            f"| {sc} | {ag} | {n} | {k / n:.0%} | {lo:.0%}-{hi:.0%} | "
            f"{sum(r['latency_s'] for r in rs) / n:.1f}s | {sum(r['tool_calls'] for r in rs) / n:.1f} | "
            f"{sum(r['tokens'] for r in rs) / n:.0f} |"
        )

    out += ["", "### Failure reasons", "", "| scenario | agent | failures |", "|---|---|---|"]
    for (sc, ag), rs in sorted(groups.items()):
        fails = Counter(r["reason"] for r in rs if not r["success"])
        out.append(f"| {sc} | {ag} | {dict(fails) or '-'} |")

    by_key = {(r["scenario"], r["agent"], r["task"], r["seed"]): r["success"] for r in rows}
    out += ["", "### Fixed / broken vs baseline (paired by task and seed)", "",
            "| scenario | agent | fixed | broken |", "|---|---|---|---|"]
    for (sc, ag) in sorted(groups):
        if ag == "baseline":
            continue
        fixed = broken = 0
        for (s2, a2, t, seed), ok in by_key.items():
            if s2 == sc and a2 == ag and (sc, "baseline", t, seed) in by_key:
                base = by_key[(sc, "baseline", t, seed)]
                fixed += (not base) and ok
                broken += base and (not ok)
        out.append(f"| {sc} | {ag} | {fixed} | {broken} |")

    cats = sorted({r["category"] for r in rows})
    agents = sorted({r["agent"] for r in rows})
    out += ["", "### Success by category (all selected scenarios)", "",
            "| category | " + " | ".join(agents) + " |", "|---|" + "---|" * len(agents)]
    for c in cats:
        cells = []
        for a in agents:
            rs = [r for r in rows if r["category"] == c and r["agent"] == a]
            cells.append(f"{sum(r['success'] for r in rs) / len(rs):.0%}" if rs else "-")
        out.append(f"| {c} | " + " | ".join(cells) + " |")

    text = "\n".join(out)
    print(text)
    with open(args.out, "w") as f:
        f.write(text + "\n")


if __name__ == "__main__":
    main()
