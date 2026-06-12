---
title: "Snowflake Cortex Analyst in practice: what the demo doesn't show you"
date: 2026-06-12
published_at: 2026-06-12T11:00:00Z
slug: snowflake-cortex-analyst-in-practice
description: "Cortex Analyst looks smooth in a demo. Here is what actually happens when you point it at a real warehouse in week two."
tags: [snowflake, analytics-engineering, ai, cortex]
read_time: 6
status: published
---


The Snowflake Cortex Analyst demo is a good demo. Curated schema, hand-picked questions, a semantic model that has been tuned to answer exactly the things the presenter is about to ask. The SQL it generates is clean. The answers are right. The audience nods.

Week two looks different. You point Cortex Analyst at your actual warehouse — the one with three overlapping definitions of "active customer," mart models whose column descriptions were last updated when the model was first built, and a pipeline that lands data at 6 AM but is sometimes an hour late. Suddenly the generated SQL is plausible-looking but wrong, or right on a metric nobody uses, or right but returning yesterday's numbers.

This post is about the gap between the demo and production. Not to say Cortex Analyst is bad — it is genuinely useful when set up correctly — but to lay out the problems you will hit and the practical steps that make it reliable.

## What Cortex Analyst actually is

Cortex Analyst takes a natural language question and returns SQL, using a semantic model YAML you define and store in Snowflake. The semantic model describes your tables, columns, metrics, and relationships. Cortex reads it, interprets the question against it, and generates a query. You approve or run the query; Cortex does not execute anything directly unless you wire it up to do so.

The semantic model is the entire ballgame. Here is a minimal example for a subscriptions table:

```yaml
name: subscription_metrics
description: "Core subscription and MRR metrics for the B2B customer base."
tables:
  - name: fct_subscriptions
    description: "One row per active subscription per month. Source of truth for MRR and churn."
    base_table:
      database: ANALYTICS
      schema: MARTS
      table: fct_subscriptions
    dimensions:
      - name: customer_id
        description: "Unique identifier for the customer account."
        expr: customer_id
        data_type: VARCHAR
      - name: plan_name
        description: "Subscription plan at time of snapshot. Values: starter, growth, enterprise."
        expr: plan_name
        data_type: VARCHAR
      - name: subscription_status
        description: "Current subscription state. Use 'active' for live subscriptions only."
        expr: subscription_status
        data_type: VARCHAR
    time_dimensions:
      - name: snapshot_month
        description: "First day of the month this snapshot represents."
        expr: snapshot_month
        data_type: DATE
    measures:
      - name: mrr
        description: "Monthly recurring revenue in USD. Sum across active subscriptions."
        expr: mrr_usd
        data_type: NUMBER
        default_aggregation: sum
```

That YAML is what Cortex reads when you ask "what was MRR last month." The description fields are not decoration — they are instructions.

## Why the demo looks easy

**Problem 1: Missing or vague dbt documentation.** Cortex Analyst reads your column descriptions to understand what each field means. If your schema.yml says `description: "the plan"` instead of something specific, Cortex guesses. It will usually guess something reasonable. It will sometimes guess wrong. In a demo, the semantic model has been written carefully. In production, you have 40 models, some documented in 2022, some not at all.

**Problem 2: Metric ambiguity.** "Active customers" probably exists in more than one mart. You might have it in `fct_subscriptions`, `fct_accounts`, and `dim_customers`, and each version filters slightly differently — one uses subscription status, one uses last login date, one counts billing accounts. Cortex Analyst picks one based on what your semantic model exposes. It does not tell the user which definition it used. The user sees a number and assumes it is the right one.

**Problem 3: Multi-join queries with window functions.** This is where generated SQL goes quietly wrong. Ask Cortex something like "show me MRR growth rate for customers who churned in Q1 and then reactivated," and you will get SQL that compiles and runs. It might even look right at a glance. Here is an example of the shape of query that tends to produce plausible-but-incorrect results:

```sql
-- Cortex-generated SQL — looks reasonable, has a subtle window framing issue
WITH churned AS (
    SELECT
        customer_id
        ,MIN(snapshot_month) AS churn_month
    FROM fct_subscriptions
    WHERE subscription_status = 'churned'
    GROUP BY customer_id
),
reactivated AS (
    SELECT
        s.customer_id
        ,s.snapshot_month
        ,s.mrr_usd
        ,LAG(s.mrr_usd) OVER (
            PARTITION BY s.customer_id
            ORDER BY s.snapshot_month
            -- Missing: no filter on status = 'active' before the window
        ) AS prev_mrr
    FROM fct_subscriptions s
    INNER JOIN churned c ON s.customer_id = c.customer_id
    WHERE s.snapshot_month > c.churn_month
)
SELECT
    customer_id
    ,(mrr_usd - prev_mrr) / NULLIF(prev_mrr, 0) AS mrr_growth_rate
FROM reactivated
WHERE prev_mrr IS NOT NULL
```

The window function runs over all rows after churn, including rows where the subscription is still dormant. The growth rate calculation is technically executing; the denominator just includes the wrong baseline. Nobody notices until someone compares the output to a manually built cohort.

**Problem 4: Data freshness.** Cortex Analyst has no awareness of your pipeline schedule. If your marts refresh at 6 AM and it is 10 PM, a question about "yesterday's revenue" returns data that closed 40 hours ago. Cortex will not say "this data is stale." It returns numbers with no timestamp context, and the user assumes they are current.

## What actually works

**Start with your mart layer, not raw or intermediate models.** Your marts are governed, tested, and documented. They are also the layer where your business definitions are already encoded. Pointing Cortex at raw Salesforce tables or intermediate staging models is a fast path to wrong answers.

**Write semantic model descriptions as if you are writing instructions for a new analyst.** The descriptions Cortex reads need to be unambiguous. Vague column names with vague descriptions produce vague SQL. The more precise your language, the more constrained the interpretation.

Here is the difference in practice:

```yaml
# Unhelpful — Cortex will guess
- name: arr
  description: "ARR value."
  expr: arr_usd
  data_type: NUMBER

# Helpful — Cortex has a specific instruction
- name: arr
  description: >
    Annual recurring revenue in USD. Calculated as MRR * 12.
    Includes active subscriptions only. Excludes one-time fees and
    professional services. Use this metric for board and investor reporting.
  expr: arr_usd
  data_type: NUMBER
  default_aggregation: sum
```

**Constrain what your semantic model exposes.** You do not have to include every mart in the semantic model. Include the marts that are well-documented, well-tested, and answer a clear set of questions. Leave out marts that are in flux or that require context a business user is unlikely to provide in a natural language question.

**Build a lightweight freshness indicator into your semantic model.** One approach is to expose a `data_as_of` dimension that pulls from a pipeline metadata table. Users can query it directly, and you can surface it in your UI layer:

```python
# Simple Streamlit snippet — surface freshness before showing results
import snowflake.connector
import streamlit as st

conn = snowflake.connector.connect(**st.secrets["snowflake"])

freshness_query = """
    SELECT MAX(snapshot_month) AS latest_snapshot
    FROM analytics.marts.fct_subscriptions
"""
cursor = conn.cursor()
cursor.execute(freshness_query)
latest = cursor.fetchone()[0]

st.caption(f"Data current through: {latest}. Pipeline runs daily at 06:00 UTC.")
```

Not elegant, but it gives users the information they need before they act on a number.

**The correct mental model:** Cortex Analyst is a natural language front-end for a governed query layer. It is not a replacement for that layer. The better your dbt semantic layer — complete descriptions, tested metrics, clean mart boundaries — the better Cortex Analyst performs. You are not configuring an AI product. You are improving your data documentation and then attaching an interface to it.

<div class="takeaways">
<h2>Takeaways</h2>
<ul>
<li><strong>The semantic model is the product</strong> — Cortex Analyst output quality is a direct function of how well you have documented your metrics and columns. Treat the YAML like production code.</li>
<li><strong>Scope the semantic model to your best marts</strong> — start with two or three well-governed, well-tested models rather than exposing everything at once.</li>
<li><strong>Write descriptions as unambiguous instructions</strong> — include what a metric includes, what it excludes, and which business context it belongs to. Vague descriptions produce vague SQL.</li>
<li><strong>Multi-join and window function queries need human review</strong> — generated SQL that compiles is not guaranteed to be correct. Add a review step for any query pattern more complex than a simple aggregation.</li>
<li><strong>Surface data freshness explicitly</strong> — Cortex has no pipeline awareness. Build a freshness indicator into your UI layer so users know what "current" actually means before they act on a number.</li>
</ul>
</div>

What is the first question you would give Cortex Analyst access to answer — and what is the one you would never let it near?
