---
title: "Why your dbt project has 47 models and nobody trusts any of them"
date: 2026-06-05
published_at: 2026-06-05T10:00:00Z
slug: dbt-47-models-nobody-trusts
description: "The dbt trust problem isn't a tooling issue. It's an architectural and process problem — and it shows up in every data team that moved fast and skipped the governance layer."
tags: [dbt, data-quality]
read_time: 7
status: published
---

Every data team I talk to eventually confesses the same thing. They adopted dbt six to eighteen months ago. The project has grown. There are models everywhere — staging, intermediate, marts, one-offs, experiments that never got cleaned up. The CI pipeline is green.

And nobody trusts the numbers.

Not Finance. Not the CSM team. Not the product manager who keeps asking for their own Snowflake access because "it's faster than waiting." The dashboards exist. The models pass tests. And yet the weekly revenue review still starts with someone pulling up a spreadsheet to double-check.

This is the dbt trust problem. It is not a tooling problem. It is an architectural and process problem that tooling alone cannot fix.

---

## How you get to 47 models

The pattern is consistent enough that I'd call it a law. It goes like this:

**Month 1–3:** A data engineer — sometimes a senior one, sometimes someone who just did the dbt Fundamentals course — sets up the project. They create a staging layer. They build a few marts. It's clean. There's hope.

**Month 4–8:** The business starts making requests faster than the model structure can absorb them. Someone adds a one-off model for a sales report. Someone else forks `fct_orders` because they need a slightly different grain. An analyst writes a model directly in the marts folder because staging felt too far away. Nobody reviews it. The CI passes.

**Month 9–18:** You now have:

- Staging models that duplicate logic from each other
- Intermediate models that exist for one downstream consumer and nowhere else
- Multiple "fct" models for the same business entity with subtly different definitions
- A `mart_finance_v2` next to `mart_finance` with no documentation explaining the difference
- Tests that check for nulls and uniqueness but not for business logic

The project is large. The project is broken in ways that are invisible to `dbt test`.

---

## The real problem is undocumented decisions

When a stakeholder looks at two numbers that disagree, they don't think "there's a SQL bug." They think "I can't trust this system." And once that trust breaks, it's very slow to rebuild.

The root cause is usually not bad SQL. It's that consequential modelling decisions were made without a record. Consider:

<pre><code><span class="comment">-- Which of these is "correct" MRR?</span>

<span class="comment">-- Version A — in mart_revenue</span>
<span class="keyword">select</span>
    date_trunc(<span class="string">'month'</span>, subscription_start) <span class="keyword">as</span> month
  , <span class="keyword">sum</span>(monthly_amount) <span class="keyword">as</span> mrr
<span class="keyword">from</span> {{ ref('stg_subscriptions') }}
<span class="keyword">where</span> status = <span class="string">'active'</span>

<span class="comment">-- Version B — in mart_finance_v2</span>
<span class="keyword">select</span>
    date_trunc(<span class="string">'month'</span>, billing_date) <span class="keyword">as</span> month
  , <span class="keyword">sum</span>(amount) <span class="keyword">as</span> mrr
<span class="keyword">from</span> {{ ref('stg_invoices') }}
<span class="keyword">where</span> payment_status = <span class="string">'paid'</span></code></pre>

Both look reasonable. They produce different numbers. Without documentation explaining the business decision behind each, every stakeholder who sees a discrepancy becomes a skeptic.

The model exists. The test passes. The trust is gone.

---

## What actually fixes it

### 1. Enforce the layer contract

The staging layer should contain exactly one model per source table, with no business logic — only renaming, casting, and deduplication. If a staging model joins two source tables, something is wrong.

The intermediate layer is where business logic lives. It is not for consumption — it exists to make marts readable. If an analyst is querying an intermediate model directly, the mart layer is missing something.

The mart layer is what stakeholders and BI tools touch. Every model here should have a documented grain, a documented owner, and documented definitions for every column that represents a business concept.

This is not a novel framework. It is what the dbt docs describe. The gap is enforcement.

<pre><code><span class="comment">-- stg_subscriptions: clean, no business logic</span>
<span class="keyword">select</span>
    subscription_id
  , customer_id
  , cast(started_at <span class="keyword">as</span> date)     <span class="keyword">as</span> started_date
  , cast(ended_at <span class="keyword">as</span> date)       <span class="keyword">as</span> ended_date
  , lower(trim(status))          <span class="keyword">as</span> status
  , amount_cents / 100.0         <span class="keyword">as</span> monthly_amount
<span class="keyword">from</span> {{ source('billing', 'subscriptions') }}</code></pre>

### 2. Write tests for business rules, not just data shape

`not_null` and `unique` are hygiene. They are not trust. Business logic errors reach dashboards because the tests were not written to catch them.

Write tests for the things that matter to stakeholders:

<pre><code><span class="comment"># schema.yml</span>
models:
  - name: fct_subscriptions
    columns:
      - name: monthly_amount
        tests:
          - not_null
          - dbt_utils.accepted_range:
              min_value: 0
              max_value: 50000
      - name: status
        tests:
          - accepted_values:
              values: [<span class="string">'active'</span>, <span class="string">'cancelled'</span>, <span class="string">'paused'</span>, <span class="string">'trialing'</span>]</code></pre>

This is the minimum. For revenue-critical models, add reconciliation tests that compare aggregate outputs across models for the same business concept.

### 3. Deprecate loudly, delete completely

The `mart_finance_v2` that nobody is supposed to use but everyone queries because it's there — delete it. Not archive it. Delete it.

Before you delete it, write a YAML description in the replacement model that says exactly what changed and why. A one-sentence note in `schema.yml` prevents 80% of the stakeholder questions that follow.

### 4. Treat the mart layer like an API

If you were building a public API, you would version it, document it, and not break consumers without notice. Your mart models are an API — Finance, RevOps, and the product team are your consumers.

This means: every mart model has a description. Every column that means something to the business has a description. Changes that affect downstream consumers go through a review. Not a formal RFC — just a human who reads the diff and asks "does anything consume this?"

In a growing company moving from spreadsheets to a proper data stack, this step is usually the one that gets skipped. It's also the one that determines whether dbt becomes the source of truth or becomes the thing the analysts work around.

---

<div class="takeaways">
<h2>Three takeaways</h2>
<ul>
<li><strong>Audit your intermediate layer for models that have exactly one downstream consumer</strong> — those belong in the mart that uses them, not as standalone files creating false structure.</li>
<li><strong>Write at least one business logic test per mart model</strong> — not a null check, an actual rule that a stakeholder would care about if violated.</li>
<li><strong>Document the definition of every revenue or retention metric at the model level</strong> — not in Confluence, not in Slack, in <code>schema.yml</code> next to the column it describes.</li>
</ul>
</div>

The project with 47 models is not a failure. It's a growth stage. The signal that you've moved past it is not a smaller model count — it's when a new analyst joins, reads the schema files, and doesn't need to ask anyone what "active customer" means.
