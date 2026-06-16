---
title: "dbt Semantic Layer vs. homegrown metric marts: when to use which"
date: 2026-06-12
published_at: 2026-06-12T12:00:00Z
slug: dbt-semantic-layer-vs-metric-marts
description: "A practical decision framework for analytics engineers choosing between pre-aggregated metric marts and the dbt Semantic Layer with MetricFlow."
tags: [dbt, AI]
read_time: 7
status: published
---

MetricFlow is production-ready. The dbt Semantic Layer has been generally available for a while now, and most analytics teams have at least one Slack thread about it. What's still missing for a lot of teams is a clear mental model for when to migrate and when a good old mart table is still the right call.

This post is that decision framework. Both approaches are valid. Both solve real problems. The question is which one fits your current situation — not which one is theoretically superior.

---

## What metric marts are

A metric mart is a pre-aggregated table: `fct_mrr`, `fct_arr`, `fct_churn_cohorts`. You compute the metric in a dbt model using SQL, materialise it as a table or incremental model, and downstream consumers — BI tools, Python notebooks, Airflow pipelines — query it directly.

The definition of the metric lives in the SQL. The result lives in the warehouse.

```sql
-- models/marts/finance/fct_mrr.sql
with subscriptions as (
    select
          subscription_id
        , customer_id
        , plan_id
        , date_trunc('month', started_at)   as cohort_month
        , date_trunc('month', cancelled_at) as churn_month
        , monthly_amount_usd
    from {{ ref('stg_subscriptions') }}
    where status in ('active', 'cancelled')
)

, spine as (
    select
          dateadd('month', seq4(), '2022-01-01'::date) as month_start
    from table(generator(rowcount => 48))
)

select
      s.month_start
    , sub.customer_id
    , sub.plan_id
    , sub.monthly_amount_usd                          as mrr
from spine s
inner join subscriptions sub
    on s.month_start >= sub.cohort_month
    and (sub.churn_month is null or s.month_start < sub.churn_month)
```

The appeal is real: this is just SQL. Anyone on the team can open it, read it, run it, and debug it. Query time is fast because the aggregation already happened at materialisation. And your BI tool does not need to know anything about MetricFlow or semantic models — it just selects from a table.

---

## What the dbt Semantic Layer is

The dbt Semantic Layer moves the metric definition out of SQL and into YAML. You declare a `semantic_model` on top of a grain-level model, define measures and dimensions, then define metrics that reference those measures. At query time, MetricFlow translates a metric query into SQL and runs it against the warehouse.

The definition lives in YAML. The result is computed on demand.

```yaml
# models/marts/finance/_semantic_models.yml
semantic_models:
  - name: subscriptions
    description: One row per subscription per month
    model: ref('fct_subscriptions_monthly')
    defaults:
      agg_time_dimension: month_start

    dimensions:
      - name: month_start
        type: time
        type_params:
          time_granularity: month
      - name: plan_id
        type: categorical
      - name: customer_segment
        type: categorical

    measures:
      - name: mrr
        description: Monthly recurring revenue in USD
        agg: sum
        expr: monthly_amount_usd

metrics:
  - name: mrr
    description: Total MRR across active subscriptions
    type: simple
    type_params:
      measure: mrr
```

Once that definition is in place, the same `mrr` metric is queryable from the dbt Cloud IDE, from Tableau via the semantic layer connector, from a Python script using the MetricFlow SDK, and — and this is the part that matters — from an LLM-backed querying layer like Cortex Analyst.

---

## The key difference

This sounds like a technical implementation detail, but it is actually a fundamental shift in where truth lives.

With a metric mart, truth is encoded in SQL and manifested as rows in a table. If your definition of MRR changes, you update the SQL, run the model, and the table changes. Every consumer gets the updated number automatically — but they were also all querying a single materialised artifact that you controlled.

With the Semantic Layer, truth is encoded in YAML and executed at query time. If your definition of MRR changes, you update the YAML. Every consumer — regardless of which tool they're using — immediately gets the new definition applied to their next query. No table refresh required. But also no pre-computed result. The warehouse does the work every time someone asks.

---

## When to use metric marts

Metric marts are the right call when your situation looks like this:

**Small team, single BI tool, stable definitions.** If you have one Tableau server and five dashboards, and MRR has not changed definition in two years, a mart table works perfectly. The complexity of MetricFlow is not justified.

**Sub-second query requirements.** Metric marts on large datasets with proper clustering will outperform query-time aggregation. If you have a dashboard that loads in 400ms and your stakeholders have noticed, do not swap it for a semantic query.

**Downstream consumers that cannot query MetricFlow.** Legacy pipelines, external vendors, read replicas with restricted access — if your consumer cannot speak MetricFlow, the Semantic Layer cannot help them.

---

## When to use the Semantic Layer

The Semantic Layer starts to pay off when your situation looks like this:

**Multiple consumers using different tools.** When Tableau, a Python model-scoring script, and a product analytics notebook all need the same MRR figure, keeping three separate implementations consistent is a maintenance tax. One YAML definition pays that tax once.

**Metric definitions change often.** If your revenue team redefines "active subscription" twice a quarter, updating three mart tables plus their downstream tests is painful. A single semantic model change propagates everywhere.

**You are building an AI querying layer.** This is the case where the Semantic Layer goes from "nice to have" to "architectural requirement."

---

## The AI querying angle

An LLM that can write SQL against your raw mart tables will eventually write wrong SQL. It will join the wrong grain, miss a filter, double-count on a fan-out. The hallucination risk is high because the LLM is operating on schema metadata alone — it has no understanding of what the measures actually represent.

A semantic model is a structured interface. The LLM reasons about metric names, dimensions, and time grains — all of which have explicit definitions. MetricFlow then translates that intent into SQL. The LLM never writes SQL directly.

```python
# Querying the Semantic Layer via MetricFlow SDK (simplified)
from dbt_metricflow.api import MetricFlowClient

client = MetricFlowClient.from_project("/path/to/dbt/project")

result = client.query(
    metrics=["mrr"],
    group_by=["metric_time__month", "customer_segment"],
    where="metric_time__month >= '2025-01-01'",
)

df = result.result_df
```

This is the architecture behind Cortex Analyst and similar governed natural-language query products. The LLM gets a governed interface. It can ask "MRR by segment for Q1" and get a correct answer because MetricFlow enforces the definition. Contrast that with an LLM generating ad-hoc SQL against `fct_mrr` — the surface area for silent errors is much larger.

---

## Migrating incrementally

You do not need to port your entire mart layer to the Semantic Layer at once. Start with one metric that has multiple consumers or that changes definition frequently. Validate that MetricFlow produces the same results as your mart table. Then expand.

Keep both approaches in production simultaneously during the transition. There is no reason to delete `fct_mrr` the day you add a semantic model for MRR. Retire the mart table when you are confident every consumer has migrated.

```yaml
# dbt_project.yml — run semantic models alongside marts with no conflict
models:
  my_project:
    marts:
      +materialized: table
      +tags: ["mart"]
    semantic:
      +materialized: view   # grain-level source models for semantic_models
      +tags: ["semantic-layer"]
```

The two approaches are not mutually exclusive during migration. That flexibility is worth using.

---

<div class="takeaways">
<h2>Takeaways</h2>
<ul>
<li><strong>Metric marts encode truth in SQL; the Semantic Layer encodes it in YAML</strong> — this is not a style preference, it determines how and when changes propagate to consumers.</li>
<li><strong>Metric marts win on query performance and simplicity</strong> — if you have one BI tool, stable definitions, and latency requirements, pre-aggregation is still the right call.</li>
<li><strong>The Semantic Layer wins when consumers multiply</strong> — three tools querying the same metric definition from one YAML file is strictly better than three copies of the same SQL.</li>
<li><strong>For AI querying layers, the Semantic Layer is an architectural requirement, not a preference</strong> — a governed interface dramatically reduces the hallucination risk versus LLM-generated ad-hoc SQL.</li>
<li><strong>Migrate incrementally, starting with one high-churn metric</strong> — pick the metric whose definition changes most often, validate parity with your mart, then expand.</li>
</ul>
</div>

---

Has your team adopted the Semantic Layer? What was the metric that finally made you switch — or what's blocking you from moving?
