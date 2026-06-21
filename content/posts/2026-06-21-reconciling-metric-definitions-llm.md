---
title: Reconciling competing metric definitions across teams with an LLM
date: 2026-06-21
published_at: '2026-06-21T21:29:05Z'
slug: reconciling-metric-definitions-llm
description: An LLM can't decide what 'active customer' means. It can find every definition
  you have, show where they diverge, and draft the doc.
tags:
- AI
- dbt
read_time: 8
status: published
---

Sales says 1,840 active customers this month. Finance says 1,510. Product says 2,260. All three numbers are in the same QBR deck. Nobody on the call can explain the gap in real time, so the meeting moves on, and three teams keep reporting three different versions of the same metric for another quarter.

This isn't a data quality bug. Every one of those numbers is computed correctly from its team's own definition — Sales counts anyone who logged in in the last 30 days, Finance counts anyone with a paid invoice in the last 90, Product counts anyone who performed a core action in the last 7. The bug is that nobody agreed on what "active" means, and nobody has a fast way to find every place that decision got made differently.

That's a genuinely good problem to hand an LLM — with a specific, narrow job description. Not "decide what active customer means." It can't, and it shouldn't get to. Its job is finding every existing definition, showing precisely where they diverge, and drafting the document that gets humans to a decision faster. The decision itself stays human.

---

## Step 1 — Inventory every definition that already exists

The definitions are never in one place. They're scattered across dbt models, BI tool calculated fields, semantic layer YAML, and a Notion doc someone wrote eighteen months ago that's now wrong. Before you can reconcile anything, you need all of them pulled into one format you can actually compare.

This is the part an LLM is well-suited for, because the inputs are heterogeneous and the extraction is a parsing-and-summarizing task, not a numerical one. Feed it a dbt model's SQL, a LookML calculated field, and a Tableau calc field, and ask it to extract the same structured shape from each:

```text
Extract this metric definition into JSON with this shape:
{ "name": str, "filter_conditions": [str], "time_window_days": int,
  "aggregation": str, "source_table": str }

Input (dbt model int_active_customers.sql):
<paste SQL>

Input (LookML, customer_explore.view.lkml):
<paste LookML>
```

The LLM is good at this specifically because each source format encodes the same concept differently — a `WHERE` clause in SQL, a filter parameter in LookML, a calculated field formula in Tableau — and normalizing across formats is exactly the kind of translation task language models handle reliably. What it should not do at this stage is judge any of them. The output is raw inventory, not analysis.

---

## Step 2 — Diff the definitions with code, not vibes

Once every definition is in the same structured shape, the comparison itself should be deterministic code, not another LLM call. This is the step people skip, and it's the one that matters most: asking an LLM "do these definitions agree?" gets you a prose answer that sounds authoritative and may or may not be checking the right fields. Diffing structured JSON objects gets you an exact, reproducible answer.

```python
def diff_definitions(defs: list[dict]) -> dict:
    return {
        "time_window_days": {d["name"]: d["time_window_days"] for d in defs},
        "aggregation": {d["name"]: d["aggregation"] for d in defs},
        "filter_conditions": {d["name"]: set(d["filter_conditions"]) for d in defs},
    }
```

Run that over the three extracted definitions and you get something unambiguous: Sales uses a 30-day window on `last_login_at`, Finance uses a 90-day window on `paid_invoice_at`, Product uses a 7-day window on `core_action_at`. That's the actual divergence, stated precisely enough that the conversation can start from "we're measuring three different behaviors over three different windows" instead of "the numbers don't match, IT must be wrong."

This is the same lesson that applies to any LLM-in-the-loop pipeline step: use the model for the part that requires language understanding — parsing heterogeneous formats — and use plain code for the part that requires correctness — comparison. Letting an LLM do the diffing too is where teams end up trusting a summary that quietly missed that one definition also excludes trial accounts and the others don't.

---

## Step 3 — Draft the reconciliation document, not the decision

With the exact divergence in hand, an LLM is a genuinely fast way to produce the first draft of the document that gets put in front of stakeholders. Not a recommendation — a structured comparison that makes the tradeoff visible:

```text
Given these three metric definitions and their exact divergence
points, write a comparison document for a stakeholder review. For
each definition: what it measures, why that team likely chose it,
and what decision it's optimized for. Do not recommend a winner.
End with three explicit open questions the group needs to resolve.
```

The "do not recommend a winner" instruction matters as much as anything else in this workflow. The LLM has no information about why Finance is contractually required to use paid-invoice activity for revenue recognition, or why Product's 7-day window matches their actual engagement loop. Those are organizational facts, not facts in the data. Let it write the comparison; let humans own the call.

---

## Step 4 — Codify the decision once it's made

Once the room agrees on a canonical definition — or agrees that "active" genuinely means three different things and needs three differently-named metrics — the unglamorous work is migrating every downstream consumer to reference the canonical version instead of recomputing its own. This is where a dbt Semantic Layer metric or a single governed `int_` model earns its keep: one place to change the definition, one place every BI tool points back to.

An LLM can speed up the migration scan: given the canonical metric and the inventory from Step 1, ask it to list every dashboard, calculated field, or model whose logic now needs to be replaced with a reference to the canonical metric. That's a search-and-flag task it handles well. Actually rewriting twenty Tableau calculated fields and confirming each dashboard still renders correctly is still a human doing the work, dashboard by dashboard.

---

## Where this breaks

- **Letting the model merge ambiguous definitions instead of surfacing them.** If you ask an LLM to "reconcile" rather than "diff," it will sometimes average or blend conflicting logic into something that satisfies neither team and is wrong for both. Keep the extraction, diff, and recommendation steps separate so this can't happen silently.
- **Treating the draft document as the decision.** The whole value of Step 3 is that it's a draft. If it gets forwarded as final without a human reviewing whether the open questions were actually answered, you've just automated the production of organizational consensus theater.
- **Definitions that were never written down anywhere extractable.** A number someone manually maintains in a spreadsheet, with the logic in their head, has nothing for the LLM to parse. The inventory step only finds what exists in a parseable form — which is itself useful information, because "this metric has no documented source" is often the actual root cause.

<div class="tradeoff-grid">
<div class="tradeoff-row header">
<div class="tradeoff-cell">Task</div>
<div class="tradeoff-cell">Good fit for an LLM</div>
<div class="tradeoff-cell">Needs a human</div>
<div class="tradeoff-cell">Why</div>
</div>
<div class="tradeoff-row">
<div class="tradeoff-cell">Extracting a definition from SQL, LookML, or a calc field</div>
<div class="tradeoff-cell">Yes</div>
<div class="tradeoff-cell">No</div>
<div class="tradeoff-cell">Parsing heterogeneous formats into a common shape is a language task</div>
</div>
<div class="tradeoff-row">
<div class="tradeoff-cell">Diffing two structured definitions</div>
<div class="tradeoff-cell">No</div>
<div class="tradeoff-cell">Code</div>
<div class="tradeoff-cell">Needs an exact, reproducible answer, not a prose summary</div>
</div>
<div class="tradeoff-row">
<div class="tradeoff-cell">Drafting the stakeholder comparison doc</div>
<div class="tradeoff-cell">Yes</div>
<div class="tradeoff-cell">Reviews it</div>
<div class="tradeoff-cell">Speeds up the writing; the framing still needs a human check</div>
</div>
<div class="tradeoff-row">
<div class="tradeoff-cell">Choosing the canonical definition</div>
<div class="tradeoff-cell">No</div>
<div class="tradeoff-cell">Yes</div>
<div class="tradeoff-cell">Requires organizational context the model doesn't have</div>
</div>
<div class="tradeoff-row">
<div class="tradeoff-cell">Finding downstream consumers to migrate</div>
<div class="tradeoff-cell">Yes</div>
<div class="tradeoff-cell">Executes it</div>
<div class="tradeoff-cell">Search-and-flag is reliable; rewriting and verifying each dashboard isn't automated</div>
</div>
</div>

<div class="takeaways">
<h2>Takeaways</h2>
<ul>
<li><strong>An LLM should never pick the canonical metric definition.</strong> That's an organizational decision with context the model doesn't have access to.</li>
<li><strong>Use the LLM to extract and normalize, not to compare.</strong> Diffing structured definitions should be deterministic code — it needs an exact answer, not a confident-sounding one.</li>
<li><strong>The highest-value output is a draft comparison document, not a recommendation.</strong> Explicitly instruct the model not to recommend a winner — that's the part that keeps the workflow honest.</li>
<li><strong>Codify the decision in one place once it's made.</strong> A dbt Semantic Layer metric or a single governed model is what stops the next divergence from happening the same way.</li>
<li><strong>This only surfaces definitions that exist in parseable form.</strong> A metric with no documented logic anywhere is itself a finding, not a gap in the workflow.</li>
</ul>
</div>

How many definitions of your most-quoted metric exist right now, and could you actually list them without asking three different people?