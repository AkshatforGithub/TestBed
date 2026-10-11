# Reliability Testbed

A fault-injecting MCP server plus an eval harness that measures how reliably LangGraph agents finish tasks when their tools fail. The harness grades by what the server actually recorded (refunds), not by what the agent says it did.

## What it tests

The backend is a fake orders service built with FastMCP. It fails on purpose in four ways:

- error: the tool raises an error
- timeout: the tool hangs
- malformed: the tool returns a broken response
- post_commit: the tool saves the refund, then raises. A naive retry refunds the customer twice.

There are 30 frozen tasks (10 dev, 20 test) across nine categories (full_refund, partial, multi, conditional, not_found, once_only, over_refund, reasoning, refuse_status). Each run is graded against the refunds the server stored, so an agent that says "done" but refunds twice still fails.

## Agents compared

- Baseline: the prebuilt LangGraph ReAct agent.
- Hardened: the same agent plus a `harden()` tool wrapper (8s timeout, 3 retries with backoff, JSON validation, idempotency key `order_id:amount`) plus a reliability system prompt.

Model: Groq `openai/gpt-oss-120b`. Per-task, per-trial fault seeds come from `zlib.crc32`.

## Results

### Dev (10 tasks x 5 trials = 50 runs per cell)

| scenario | baseline | hardened |
|---|---|---|
| clean | 96% | 100% |
| mixed_30 | 88% | 100% |
| post_commit | 70% (15 double refunds in 50) | 100% |

Paired by task and seed, hardened fixed 2 / 6 / 15 runs and broke 0 / 0 / 0 (clean / mixed_30 / post_commit). On dev, `post_commit` double refunds went from 15/50 to 0/50.

### Test (post_commit only, 1 trial per task, seed 0, 20 tasks per agent)

| agent | success | double refunds |
|---|---|---|
| baseline | 18/20 (90%) | 2 (both in full_refund) |
| hardened | 20/20 (100%) | 0 |

The original hardened run was 19/20: one trial (t28, seed 0) crashed inside the harness (`UnboundLocalError`, 0 tool calls). That was a harness bug, not an agent result. After fixing the harness I reran only that trial, and it passed, so the rerun counts. Real passes and failures were never rerun. The original run is kept in `results/runs_test_original.jsonl`. One baseline crash (t25, seed 2) is outside the seed-0 comparison.

Only post_commit was run on test, because the free-tier token limit (200K/day) ran out before other scenarios could be run.

This is consistent with dev but is not proof on its own: 2/20 vs 0/20 gives Fisher p of about 0.49 and the confidence intervals overlap (baseline 70-97%, hardened 84-100%). The test full_refund category has only a couple of tasks, so the 0% baseline there is a tiny sample. On dev, full_refund was also the weakest category (63%).

I do not claim the hardened agent is reliable. The claim is 0 failures in 20 test runs and 0 in 50 dev post_commit runs.

## What went wrong (and how it was fixed)

1. The first baseline looked near-perfect. Fault seeds took only 3 values, so every task in a trial shared the same fault rolls. I switched to per-task, per-trial seeding. The old results are kept as `runs_v1_shared_seeds.jsonl`.
2. The refund tool's docstring hinted at `idempotency_key`, which gave the baseline the hardened agent's trick. I removed the hint.
3. `build_hardened` had no model argument, which would have crashed every hardened run. I caught it before spending any API calls.
4. Parallel runs triggered Groq 429s. I unwrapped the ExceptionGroup, added 429 retry, and ran at concurrency 1.
5. The `out` UnboundLocalError in `run_eval._attempt`. Fix: initialise `out = None` before the timer starts and raise a RuntimeError if the session closes without output.
6. A mixed_40 run was discarded: the primary model hit its token limit and the fallback model returned 404, so those runs measured infrastructure, not agents. They were removed from `results/runs.jsonl`.

## Limitations and future work

- Hardened is wrapper plus extra prompt, so the gain is not attributable to the tool layer alone. A wrapper-only and a prompt-only ablation were planned but not run.
- Dev is saturated at 100% for hardened, so it can no longer discriminate between versions.
- Test covers only post_commit. clean, mixed and the other fault types were not run on test.
- Sample sizes are small (50 runs per dev cell, 20 per test cell).
- The baseline's 2 failures in the clean dev scenario had no faults, so noise or the prompt, not the faults, explains them.
- The idempotency key `order_id:amount` would block a legitimate second refund of the same amount on the same order.
- The wrapper retries policy rejections as if they were outages. A retryable vs non-retryable split was not done.
- Float amount handling and the `retries=0` edge case are untested.
- The two zero-tool-call crashes were never root-caused. The rerun passed, so a transient cause is likely, but unconfirmed.

## Rules followed

The agents, prompts and server were frozen before the test set was run, and no changes were made after seeing test results. Any wrapper change would be a new version with its own dev run.
