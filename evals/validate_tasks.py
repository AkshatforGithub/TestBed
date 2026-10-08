"""Validate the eval set, and freeze/verify it with a SHA-256 hash.

  python evals/validate_tasks.py            # validate + check against the frozen hash
  python evals/validate_tasks.py --freeze   # write the hash (do this once, before the baseline run)
"""
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from testbed import config  # noqa: E402


def main() -> int:
    raw = config.TASKS_PATH.read_bytes()
    tasks = [json.loads(line) for line in raw.decode().splitlines() if line.strip()]
    db = json.loads(config.DB_PATH.read_text())
    errors = []

    ids = [t["id"] for t in tasks]
    if len(ids) != len(set(ids)):
        errors.append("duplicate task ids")
    for t in tasks:
        for key in ("id", "category", "split", "prompt", "expect"):
            if key not in t:
                errors.append(f"{t.get('id')}: missing {key}")
        if t.get("split") not in ("dev", "test"):
            errors.append(f"{t['id']}: bad split")
        for r in t.get("expect", []):
            order = db.get(r["order_id"])
            if order is None:
                errors.append(f"{t['id']}: expects refund on unknown order {r['order_id']}")
            elif r["amount"] > order["total"]:
                errors.append(f"{t['id']}: expected refund exceeds total")

    print(f"{len(tasks)} tasks | splits {dict(Counter(t['split'] for t in tasks))}")
    print(f"categories {dict(Counter(t['category'] for t in tasks))}")

    digest = hashlib.sha256(raw).hexdigest()
    if "--freeze" in sys.argv:
        config.TASKS_HASH_PATH.write_text(digest + "\n")
        print(f"frozen: {digest[:16]}...")
    elif config.TASKS_HASH_PATH.exists():
        if config.TASKS_HASH_PATH.read_text().strip() != digest:
            errors.append("eval set changed since it was frozen")
        else:
            print("matches frozen hash")
    else:
        print("not frozen yet (run with --freeze before the baseline)")

    for e in errors:
        print("ERROR:", e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
