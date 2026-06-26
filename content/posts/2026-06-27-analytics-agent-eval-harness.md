---
title: 'How to know if your analytics agent still works: a deterministic eval harness'
date: 2026-06-27
published_at: '2026-06-26T22:34:28Z'
slug: analytics-agent-eval-harness
description: Scoring, cost tracking from real runs, and regression gating for a dbt
  analytics agent — without LLM-as-judge.
tags:
- AI
- dbt
read_time: 11
status: published
---

There's a moment in every AI project where you've run the thing enough times that it feels like it works, and you ship it. Then three weeks later someone changes the system prompt, or swaps to a newer model, or tweaks one of the tools — and the thing quietly gets worse. Nobody notices until a user says something.

That's not a hypothetical. My previous project, [dbt-agentic-engine](https://github.com/PZawieja/dbt-agentic-engine), ended with a manual sanity check: I ran 15 eval questions live, read the answers, wrote down a pass/fail in a doc. That's not repeatable, it's not scored, and it has no memory — there's nothing to compare against the next time someone changes something.

[llmops-eval-harness](https://github.com/PZawieja/llmops-eval-harness) turns "I manually sanity-checked 15 questions once" into a repeatable, scored, cost-aware check that can gate future changes. This post is a build log: what I built, why I made the tradeoffs I did, and what the first real run actually showed.

---

## The problem with manually checking

When you run an LLM agent by hand to see if it's working, you're doing three things wrong.

**You're not measuring anything.** "The answer looked right" is not a score. It tells you nothing about whether the answer was better or worse than last week, or how it compares on the questions you didn't happen to check this time.

**You're not tracking cost.** Per-question token counts in a trace file are not the same as "the full eval set cost $X to run." You need to multiply by actual pricing, sum across all questions, and compare runs. That calculation never happens manually because it's tedious.

**You have no baseline.** If you change the model from Sonnet 4.6 to Sonnet 4.7, or rewrite the system prompt, or add a tool — did accuracy go up or down? By how much? You have no idea, because you didn't record the starting point.

The harness fixes all three.

---

## Coupling to project 1 without importing it

The harness and the agent live in separate repos. That's intentional: project 1 is a working product with its own dependencies; I don't want to create a shared package or a monorepo just to run evals.

The coupling happens through one narrow contract: the harness shells out to `agent/cli.py` per question, captures its stdout as a single JSON object, and parses it.

```python
proc = subprocess.run(
    ["uv", "run", "python", "cli.py",
     "--question", question_text, "--question-id", question_id],
    cwd=agent_dir,
    capture_output=True,
    text=True,
    timeout=120,
)
result = json.loads(proc.stdout.strip().splitlines()[-1])
```

The CLI itself is eight lines:

```python
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--question", required=True)
    parser.add_argument("--question-id", default="cli-adhoc")
    args = parser.parse_args()

    result = agent_loop.run_question(args.question, question_id=args.question_id)
    print(json.dumps(result))
```

The agent loop still appends to `traces/trace_log.jsonl` exactly as it does for the Streamlit app — the harness doesn't change any agent behavior, it just adds a way to invoke the agent programmatically and read its output. The JSON shape is the same `run_question()` return dict: `final_answer`, `trace`, `tool_calls_made`, `hit_cap`, `stop_reason`, `total_usage`, `run_id`.

One fragile part: if the agent prints debug output to stdout before the JSON, parsing the last line is a workaround. The cleaner fix is for the CLI to use stderr for everything except the JSON result. That's a project-1 change I flagged but didn't make — the workaround works for now and the fix is obvious if it ever breaks.

---

## Scoring: deterministic, no LLM-as-judge

The eval question set has three tiers, each scored differently.

**Lookup and investigation questions** have either `expected_data` (structured key→value facts) or `expected_answer` (a comma-separated list of things the answer should mention). Score = fraction of expected facts found as substrings in the agent's `final_answer`.

```yaml
- id: q06
  tier: investigation
  question: "Why did Acme Co's MRR increase in April 2025?"
  expected_data:
    mar_mrr: 800.00
    apr_mrr: 2400.00
    delta: 1600.00
    event_id: E001
    event_type: plan_upgrade
```

Numbers get formatting tolerance: `800` matches `800.00` matches `$800` matches `$800.00`. If the agent says "MRR jumped from $800 to $2,400" it finds `mar_mrr` and `apr_mrr` even though the format differs from the YAML values.

```python
def _number_variants(value: str) -> set[str]:
    num = float(value.strip().lstrip("$").replace(",", ""))
    bases = {f"{num:.2f}"}
    if num == int(num):
        bases.add(str(int(num)))
        bases.add(f"{int(num):,}")
    bases.add(f"{num:,.2f}")
    variants = set()
    for b in bases:
        variants.add(b)
        variants.add(f"${b}")
    return variants
```

**Unanswerable questions** are scored by a decline-phrase heuristic: pass if the answer matches a regex like `outside (the|this) scope|doesn't track|no (model|table|field)|not tracked here` *and* contains no fabricated figure (a dollar amount or percentage). The fabricated-figure check is important — an agent that says "this data isn't tracked, but it's probably around $50,000" should fail, not pass.

```python
_DECLINE_RE = re.compile(
    r"outside (the |this )?scope|doesn'?t track|do(es)?n'?t (have|contain)"
    r"|no (model|data|entity|table|field)|not tracked( here)?",
    re.IGNORECASE,
)
_FABRICATED_FIGURE_RE = re.compile(r"\$\s?\d|\d+(\.\d+)?\s*%")

def score_unanswerable(final_answer: str) -> dict:
    declines = bool(_DECLINE_RE.search(final_answer))
    fabricated = bool(_FABRICATED_FIGURE_RE.search(final_answer))
    passed = declines and not fabricated
    return {"score": 1.0 if passed else 0.0, "passed": passed, ...}
```

I deliberately didn't use LLM-as-judge in v1. The reasons: it adds cost to every eval run, it introduces non-determinism (the judge can disagree with itself), and it's overkill when your answers are structured enough to substring-match. The spec explicitly notes that if the decline heuristic proves too brittle — false negatives on correct declines phrased unexpectedly — the fix is LLM-as-judge for the unanswerable tier specifically, not a bigger regex.

---

## Cost tracking from actual runs

The spec rule is: cost and latency are reported, not assumed. That means no estimates — every cost number in the output came from a real API call with real token counts.

The agent loop already accumulates token usage across all tool calls per question. The harness just multiplies:

```python
INPUT_PRICE_PER_MTOK = 3.00   # Claude Sonnet 4.6, sourced June 2026
OUTPUT_PRICE_PER_MTOK = 15.00

def compute_cost(total_usage: dict) -> dict:
    input_cost = total_usage["input_tokens"] / 1_000_000 * INPUT_PRICE_PER_MTOK
    output_cost = total_usage["output_tokens"] / 1_000_000 * OUTPUT_PRICE_PER_MTOK
    return {
        "input_tokens": total_usage["input_tokens"],
        "output_tokens": total_usage["output_tokens"],
        "input_cost_usd": round(input_cost, 6),
        "output_cost_usd": round(output_cost, 6),
        "total_cost_usd": round(input_cost + output_cost, 6),
    }
```

Pricing lives in `config.py` as named constants. If Anthropic changes the price, there's one line to update. It's not buried in a formula somewhere.

Latency works the same way: wall-clock time per question is measured around the subprocess call; per-tool-call `latency_ms` is already in every trace record the agent returns. Both are reported, not one or the other.

---

## Regression gating

The first run writes `results/baseline.json`. Every subsequent run with `--gate` compares against that baseline and exits non-zero if any of three conditions are met:

- Accuracy dropped more than 5 percentage points
- Total cost rose more than 20%
- Total latency rose more than 20%

```python
def evaluate_gate(report: dict, baseline: dict) -> dict:
    reasons = []

    accuracy_drop = baseline["accuracy_pct"] - report["accuracy_pct"]
    if accuracy_drop > MAX_ACCURACY_DROP_PCT:
        reasons.append(
            f"accuracy dropped {accuracy_drop:.1f} points "
            f"({baseline['accuracy_pct']:.1f}% -> {report['accuracy_pct']:.1f}%), "
            f"exceeds max allowed drop of {MAX_ACCURACY_DROP_PCT}"
        )

    if baseline["total_cost_usd"] > 0:
        cost_increase_pct = (
            (report["total_cost_usd"] - baseline["total_cost_usd"])
            / baseline["total_cost_usd"] * 100
        )
        if cost_increase_pct > MAX_COST_INCREASE_PCT:
            reasons.append(...)

    return {"passed": not reasons, "reasons": reasons}
```

`MAX_ACCURACY_DROP_PCT`, `MAX_COST_INCREASE_PCT`, `MAX_LATENCY_INCREASE_PCT` are defined once in `config.py`. The CLAUDE.md for this project says hard caps are config values, not buried — that rule exists because I've seen analytics code where a threshold that matters is sitting in the middle of a function nobody will ever look at.

One sharp edge: `--gate` and `--update-baseline` together on the same run do nothing useful. The gate compares the current run against the existing baseline before the update — if you're updating, you're declaring this run *is* the new standard, so gating against the old one is meaningless. The harness warns and exits cleanly in that case.

---

## What the first real run showed

Running all 15 questions live against the agent:

```
id   tier           pass  score  cost_usd  latency_ms  tools (actual/est)
---  -------------  ----  -----  --------  ----------  ------------------
q01  lookup         PASS  1.00   0.0113    5968        1/1
q02  lookup         PASS  1.00   0.0172    8868        1/1
q03  lookup         PASS  1.00   0.0331    15656       3/1
q04  lookup         FAIL  0.00   0.0117    5661        1/1
q05  lookup         PASS  1.00   0.0161    7037        2/1
q06  investigation  FAIL  0.00   0.0420    13702       6/3
q07  investigation  FAIL  0.00   0.0426    12895       6/3
q08  investigation  FAIL  0.50   0.0526    24911       6/3
q09  investigation  FAIL  0.00   0.0177    9090        3/3
q10  investigation  FAIL  0.75   0.0494    19901       5/3
q11  investigation  FAIL  0.40   0.0462    18682       5/3
q12  investigation  FAIL  0.50   0.0582    25338       6/3
q13  unanswerable   PASS  1.00   0.0052    4123        0/0-2
q14  unanswerable   PASS  1.00   0.0051    3427        0/0-1
q15  unanswerable   PASS  1.00   0.0148    7593        1/0-2

accuracy: 46.7%  (7/15 scored questions passed)
total cost: $0.4232
total latency: 182852ms
```

46.7% is not a good score, but it's an honest one. Two distinct failure modes showed up immediately.

**The 6-tool-call cap is too low for investigation questions.** q06 and q07 hit the cap and returned the partial-findings fallback before finishing their cross-mart analysis. q08 burned two calls on a wrong column name (`mrr` instead of `mrr_amount`), leaving the budget exhausted before it could pull the contract events. The cap is a project-1 config value set deliberately — the spec says agents that hit it should say so rather than guess — but 6 calls is genuinely not enough for questions that need to check the MRR mart, the logo mart, and the contract events table in sequence. That's a project-1 tuning decision, not a harness bug.

**`expected_answer` substring matching fails on semantically correct answers.** q04 asked whether all tests pass for `fct_mrr_bridge_monthly`. The agent answered correctly — "Yes, all 7 tests currently pass for `fct_mrr_bridge_monthly`..." — but the expected_answer started with "Yes — all 7 tests pass (6 not_null tests on month_date/new_mrr/...)" and the scoring looks for that as a substring. Different phrasing, correct answer, zero score.

q09 had the same problem: expected "No — all tests pass across all three marts as of the last dbt build," agent said "All three marts are fully clean as of the last dbt build. No failing tests anywhere" — again correct, but no substring match.

The fix for q04 and q09 is to replace `expected_answer` with `expected_data` (structured key→value) for questions where the phrasing can vary. `expected_data` is how the investigation-tier questions are structured — it's why q10 scored 0.75 (3 of 4 facts found) instead of 0.00 even with a partial answer. The evaluation set needs updating, not the scoring logic.

The unanswerable tier was clean: 3/3, no fabricated figures, all correctly declined. That was the tier I was most uncertain about — the heuristic felt brittle when I wrote it — and it held up on first contact.

---

## The part that's missing from most eval write-ups

Most posts about LLM evaluation describe the methodology. They don't publish the score.

The score from the first run of this harness is 46.7%. That's worse than I expected when I was writing the question set by hand and qualitatively checking answers. The discrepancy is partly the scoring tool (two questions failed on substring matching despite correct answers), and partly the agent genuinely struggling with multi-hop investigation questions under a conservative tool-call budget.

Both findings are useful. The scoring limitation tells me `expected_answer` is the wrong format for questions where phrasing varies. The agent limitation tells me the tool-call cap needs revisiting before investigation-tier accuracy will improve. Neither of those insights was available from the manual sanity check.

That's the point of running the harness: the score tells you something the manual check doesn't, even when — especially when — the number is lower than you wanted.

---

<div class="takeaways">
<h2>Takeaways</h2>
<ul>
<li><strong>A manual sanity check has no memory.</strong> It can't tell you if this run is better or worse than last week, and it can't stop a silent regression from shipping.</li>
<li><strong>Deterministic scoring is good enough for v1.</strong> Substring matching with number-formatting tolerance catches real failures without the cost, non-determinism, and complexity of LLM-as-judge.</li>
<li><strong><code>expected_data</code> is more robust than <code>expected_answer</code>.</strong> Structured key→value facts let you check specific numbers and terms without requiring the exact phrasing the eval author happened to write down.</li>
<li><strong>Cost is a first-class metric, not an afterthought.</strong> Running 15 questions cost $0.42 from actual token counts — not an estimate. That number exists to be compared against future runs, not to be impressive or alarming.</li>
<li><strong>Put thresholds in one visible place.</strong> Accuracy drop tolerance, cost ceiling, latency ceiling — all named constants in <code>config.py</code>. A threshold buried inside a function is a threshold nobody will update when the project changes.</li>
<li><strong>Publish the actual score.</strong> 46.7% on the first run. That number revealed two concrete problems: a scoring format issue on two questions, and a tool-call budget that's too low for multi-hop investigation questions. The manual check didn't surface either.</li>
</ul>
</div>

If you've shipped an AI feature and you're not running a scored eval on it regularly, what's your actual evidence that it still works?