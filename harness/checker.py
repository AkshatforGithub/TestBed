"""Deterministic grading: compare the refunds the server actually recorded to the expected ones."""
import json
from collections import Counter


def _norm(refunds):
    return [(r["order_id"], round(float(r["amount"]), 2)) for r in refunds]


def read_refunds(state_path) -> list[dict]:
    try:
        with open(state_path) as f:
            return json.load(f)["refunds"]
    except (OSError, ValueError, KeyError):
        return []


def diagnose(got, expect) -> str:
    """'ok' or the failure type: double_refund / wrong_refund / unexpected_refund / missing_refund."""
    g, e = Counter(_norm(got)), Counter(_norm(expect))
    if g == e:
        return "ok"
    extra, missing = g - e, e - g
    if any(k in e and g[k] > e[k] for k in extra):
        return "double_refund"
    if extra and missing:
        return "wrong_refund"
    if extra:
        return "unexpected_refund"
    return "missing_refund"
