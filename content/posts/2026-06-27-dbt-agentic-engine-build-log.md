---
title: 'Building an analytics agent on a real dbt project: what actually broke'
date: 2026-06-27
published_at: '2026-06-26T22:38:39Z'
slug: dbt-agentic-engine-build-log
description: A build log for dbt-agentic-engine — four tools, a hard call budget,
  a structured trace, and the things that only broke on live API calls.
tags:
- AI
- dbt
read_time: 11
status: published
---

Most analytics agent demos work like this: the model receives a question, generates SQL, runs it, returns an answer. If the question is simple enough, that works fine. If the question is "why did this customer's logo count drop in July" — which requires checking the logo mart, the MRR mart, and the contract events table and cross-referencing them — a single SQL generation step doesn't get there.

[dbt-agentic-engine](https://github.com/PZawieja/dbt-agentic-engine) is a four-tool agent that chains multiple tool calls to investigate analytics questions against a real dbt project. The distinguishing feature isn't the chat interface — it's the structured execution trace it logs per question, which is what makes the follow-on project ([an eval harness that scores and cost-tracks live runs](https://goldlayer.dev/writing/analytics-agent-eval-harness.html)) possible at all.

This post is a build log: the design decisions, what broke (several things), and what the manual sanity check at the end actually showed.

---

## Four tools, not forty

The agent has exactly four tools:

| Tool | What it does |
|---|---|
| `list_models()` | dbt model names, layer (staging/intermediate/marts), one-line description |
| `get_model_columns(model_name)` | column names, types, and descriptions for a model |
| `run_query(sql)` | runs a SELECT against the DuckDB warehouse |
| `get_test_results(model_name)` | dbt test pass/fail status as of the last `dbt build` |

The question I kept coming back to when designing the toolbelt was: what is the smallest set of tools that lets the model investigate a question it couldn't answer with one query? `list_models` tells it what data exists. `get_model_columns` tells it how to query a model without guessing. `run_query` lets it actually look at data. `get_test_results` lets it answer questions about data quality.

Four tools cover lookup questions (one call, already in the schema), investigation questions (cross-mart, 3–5 calls), and unanswerable questions (1–2 verification calls before a correct decline). A fifth tool for schema exploration or a sixth for dbt lineage would add surface area without changing what the agent can actually answer. Keep the toolbelt narrow until a real question breaks it.

---

## SELECT-only enforcement at the connection, not the prompt

The spec requirement is: run_query must be enforced SELECT-only at the connection level, not by instructing the model or checking the SQL text.

Why not a string check? Because a string check on SQL is always leaky. `SELECT * FROM t; INSERT INTO ...` passes a "starts with SELECT" test. A model creative enough to try a SQL injection path would also be creative enough to get past a keyword check. And more practically: "trust me, I told it not to" is not something you can explain to a security review.

The implementation is two lines:

```python
_read_only_con = duckdb.connect(str(WAREHOUSE_PATH), read_only=True)
```

DuckDB raises a `duckdb.Error` on any CREATE/INSERT/UPDATE/DELETE/DROP statement before executing it, at the engine level. Not a string check — the engine itself refuses. If the agent sends a non-SELECT statement, `run_query` returns an error dict and the model learns from that in the next step.

One thing that isn't covered: a SELECT that pulls PII. There's no PII column scan here. The warehouse is seeded data with fictional companies, so this wasn't a live risk for this project. A real deployment would need that layer — [Revenue Intelligence Agent](https://goldlayer.dev/writing/revenue-intelligence-agent-ai-cs-copilot.html) implemented one, this project didn't.

---

## The tool-call budget

Every question gets a hard cap of 6 tool calls. If the agent hits the cap before finding an answer, it returns a partial-findings response that says so explicitly:

```python
if tool_calls_made >= max_tool_calls:
    return _result(
        run_id, question_id, question,
        f"Could not complete within the {max_tool_calls}-tool-call budget. "
        f"Returning partial findings from the {len(trace)} tool call(s) made so far.",
        trace, True, "tool_call_budget_exceeded", total_usage, started_at,
    )
```

Six is conservative. Investigation questions that need to check three marts and cross-reference a contract events table use 3–5 calls cleanly. Six leaves room for one recovery call if the model guesses a column name wrong and needs to use `get_model_columns` to correct course. In practice, complex investigation questions sometimes still hit the cap — because the model sometimes guesses *two* column names wrong before checking the schema. More on that below.

The cap is a named constant: `MAX_TOOL_CALLS = 6`. It's not buried in the while loop. If the right number turns out to be 8 after the eval harness runs, that's one line to change.

---

## The structured trace

Every tool call is logged to `traces/trace_log.jsonl` — one JSON record per line, appended by `trace_log.write_trace_record()`. The summary record at the end of each question adds the totals: run_id, final_answer, tool_calls_made, total_usage, started_at, completed_at.

This is the format of a tool_call record:

```text
{
  "record_type": "tool_call",
  "run_id": "5238f05b99ab4907a82061beae5e965b",
  "step": 1,
  "question_id": "q01",
  "tool_name": "get_model_columns",
  "input": {"model_name": "fct_mrr_monthly"},
  "output": {"model": "fct_mrr_monthly", "columns": [...]},
  "error": null,
  "latency_ms": 489.46,
  "usage": {"input_tokens": 1268, "output_tokens": 64},
  "timestamp": "2026-06-26T21:18:44.506939+00:00"
}
```

The trace is a first-class deliverable, not a debug artifact. It's what lets the eval harness compute per-tool latency sums, verify whether the agent hit the cap, and feed cost calculations from actual token counts rather than estimates. A system that logs answers but not traces has no way to explain why an answer was wrong or expensive.

JSON Lines over a flat file was a deliberate choice over a DuckDB table. The agent enforces no write access to the project's own warehouse — `read_only=True` on the connection. Introducing a separate writable connection just for trace logging would be a second code path to maintain for no real benefit. The flat file appends atomically, diffs cleanly when a sample trace is committed, and is queryable directly: `jq` for ad-hoc filtering, or DuckDB's `read_json_auto('traces/trace_log.jsonl')` for anything heavier.

---

## What actually broke

The decisions log is the honest account. These are the failures that only showed up under the conditions that actually matter.

**`json.dumps` crashed on the first live API call.** DuckDB returns native `datetime.date` and `decimal.Decimal` objects from its cursor. Those aren't JSON-serializable. The tool-level unit tests never caught this because they printed results rather than round-tripping them through the agent loop's `json.dumps`. The fix was to stringify non-JSON-native types at the source in `tools.py` — not a `default=str` patch at each call site — so every consumer (the agent loop, the trace log) gets safe values automatically. The lesson: printing a result and serializing it through the actual consumer are different tests.

**Bare table names failed silently.** DuckDB requires schema-qualified names (`main_marts.fct_mrr_monthly`) by default. Without a `search_path`, any `run_query` call using a bare model name returned a "table not found" error. The agent would then waste a tool call on `list_models`, confirm the model exists, and try the same query again with the same error — burning budget for no progress. Fixed by running `SET search_path = 'main_marts,main_intermediate,main_staging,main_raw'` once when the connection opens. Caught by actually calling `run_query` with realistic SQL during testing, not by inspecting the code.

**A pre-commit hook silently rewrote all commas.** The project enforces leading commas in SQL — a non-negotiable style rule, consistent with the portfolio's SQL conventions. A local pre-commit hook ran `sqlfluff fix` on staged `.sql` files before commit. Without a `.sqlfluff` config in the repo, sqlfluff's default `LT04` policy is *trailing* commas. The very first dbt commit silently rewrote every model to trailing commas on the way in. Caught immediately after committing by reading the diff the hook produced. Fixed by adding `.sqlfluff` at the repo root with `line_position = leading` under `[sqlfluff:layout:type:comma]`, then running a corrective commit. The lesson: a pre-commit hook that auto-fixes is a second author with its own opinions. Check its diff after every commit until a config file pins its behavior.

**CLAUDE.md was committed and pushed to a public repo.** CLAUDE.md contains private project instructions that aren't meant for public consumption. It was committed in the very first commit before the gitignore entry was added. Caught on reviewing what gets pushed in a later phase. Fixed with `git filter-repo` to strip the file from every commit in history, then a force push. `git filter-repo` requires a clean working tree — it silently discarded uncommitted changes to `agent_loop.py` in the process. Recovered from a backup taken immediately before running the rewrite. The practical rule: take a full repo backup before any history rewrite, not just a copy of the file being removed, and expect the clean-working-tree precondition to cost you anything uncommitted. Also: always verify which of a template/real-file pair actually received the secret before trusting "it's gitignored."

---

## Model stochasticity: the agent sometimes guesses wrong

The system prompt includes an explicit instruction: check column names with `get_model_columns` before writing SQL, unless you already confirmed them in this conversation. Adding that instruction reduced column-name guessing measurably. It didn't eliminate it.

Across live runs of the same investigation question, the agent ranged from a clean 3-call resolution (check schema, run query on mart A, run query on mart B, done) to exhausting the 6-call budget on Binder Errors from guessed column names before landing on a correct or partial answer. The same question, the same prompt, the same model, different outcomes. That's real stochasticity — it's not a bug in the loop that more prompt engineering will reliably fix.

This is the reason the eval harness exists as a separate project. A manual sanity check can't tell you what fraction of runs hit the cap vs. complete cleanly, or what a systematic prompt change does to that distribution across 15 questions. The [eval harness](https://goldlayer.dev/writing/analytics-agent-eval-harness.html) can.

---

## The data design

The warehouse is a fictional B2B SaaS subscription dataset, built entirely from seeded CSVs. The data was designed to carry five specific events that investigation-tier questions are built around:

- A plan upgrade (MRR increase, same customer, same subscription)
- A contract transfer from an acquisition (not real churn, not real new business — one contract, two customer IDs)
- A delayed invoice (revenue recognized a month late — timing issue, not a real revenue change)
- A new logo signing
- A cancellation that takes effect on the last day of a month (churn recorded in the *next* month, not the cancellation month)

Each event creates a question that looks straightforward on a dashboard but requires cross-referencing at least two marts to explain correctly. "Initech's logo count dropped in July" looks like churn until you query the MRR mart and see the subscription MRR held flat under a different customer ID. That's the scenario a one-shot SQL agent can't navigate without calling multiple tools.

The dbt project follows a standard medallion shape:

```
seeds/           raw_customers, raw_subscriptions, raw_line_items,
                 raw_contract_events, raw_invoices
staging/         stg_ models — 1:1 with seeds, casting and renaming only
intermediate/    int_ models — business logic, monthly spine, MRR calculations
marts/           dim_customers, fct_mrr_monthly, fct_mrr_bridge_monthly,
                 fct_contract_events, fct_customer_logo_monthly,
                 fct_revenue_recognized_monthly
```

Every mart model has `not_null` and `unique` tests on its primary key, and a one-line description in `schema.yml`. The test suite covers 113 tests total, all passing. This matters for the eval set: q09 asks whether the marts have failing tests, and a correct "no" answer requires the tests to actually be written.

---

<div class="takeaways">
<h2>Takeaways</h2>
<ul>
<li><strong>Four tools cover more than you'd expect.</strong> List, columns, query, test results — that's enough to answer lookup, investigation, and unanswerable questions across a real dbt project. Add tools when a real question breaks the toolbelt, not in advance.</li>
<li><strong>Enforce SELECT-only at the connection, not the prompt.</strong> <code>duckdb.connect(read_only=True)</code> is an engine-level guarantee. A system prompt saying "don't write data" is not.</li>
<li><strong>The trace is a first-class deliverable.</strong> Per-call latency, token usage, input, output, error — logged for every tool call. Without it, you can't explain why an answer was expensive or wrong, and you can't build a scored eval harness on top.</li>
<li><strong>Non-JSON-native types from DuckDB only break when you serialize them.</strong> Printing a tool result and round-tripping it through <code>json.dumps</code> are different tests. Run the actual consumer path in tests, not just the tool in isolation.</li>
<li><strong>A pre-commit hook that auto-fixes is a second author.</strong> Verify its output after the first few commits. A config file that pins its behavior is not optional if the hook's defaults conflict with the project's conventions.</li>
<li><strong>Model stochasticity is real and prompt engineering has diminishing returns.</strong> The agent's column-guessing behavior improved with a system prompt nudge and then stopped improving. Measure the residual failure rate with a scored eval harness; don't try to prompt it to zero.</li>
<li><strong>Design your seeded data around the questions you want to ask.</strong> Each event in the dataset exists because it creates a scenario that requires cross-mart reasoning to explain — the contract transfer, the delayed invoice, the end-of-month cancellation. Straightforward data produces straightforward demos.</li>
</ul>
</div>

What's the hardest analytics question your team regularly fails to answer without an analyst in the room — and which of those requires cross-referencing more than one source to explain?