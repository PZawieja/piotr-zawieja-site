---
title: "How to write dbt tests that catch real business logic errors (not just nulls)"
date: 2026-06-12
published_at: 2026-06-12T13:00:00Z
slug: dbt-tests-business-logic-errors
description: "Most dbt test suites catch infrastructure failures like nulls and duplicate keys, but miss the business logic errors that surface in weekly business reviews."
tags: [dbt, analytics-engineering, data-quality, sql]
read_time: 6
status: published
---


The test suite is green. CI passed. The model ran clean. Then the weekly business review starts and someone says "these numbers look wrong."

You pull the query. The data is there, not null, no duplicates, all foreign keys resolve. Everything your tests checked is fine. The numbers are still wrong — a filter on the wrong date field, a metric that excludes a subscription type added last month, a calculation that silently started returning zero for a cohort nobody thought to check.

This is the dbt testing gap. Most projects test data shape. Very few test data meaning. `not_null` and `unique` are necessary — without them you are flying completely blind. But they are not sufficient, and in practice they give teams a false sense of coverage that makes the wrong-number conversation much more painful than it needs to be.

## What most dbt test suites actually cover

The default dbt test vocabulary — `not_null`, `unique`, `accepted_values`, `relationships` — maps almost perfectly onto infrastructure failures. Missing data. Duplicate keys. Broken foreign keys. Values outside an enumerated set.

These tests answer the question: did the pipeline run correctly? They do not answer the question: did the pipeline produce the right output?

A column can be not-null, unique, and completely wrong from a business perspective. A revenue figure can be populated with plausible-looking numbers that are off by 30% because a new product line was excluded from the mart filter. A churn rate can be technically non-null and technically within an accepted value range while being calculated against the wrong date boundary for three months running.

The tests that catch infrastructure failures are worth keeping. The gap is the layer above them.

## Three categories of tests that matter

### Category 1: Range and threshold tests

The first place to add business logic coverage is financial and metric columns. Use `dbt_utils.accepted_range` to set floor and ceiling values that reflect what the number should actually be — not just that it exists.

```yaml
# models/marts/schema.yml
models:
  - name: fct_subscriptions
    columns:
      - name: monthly_amount
        tests:
          - not_null
          - dbt_utils.accepted_range:
              min_value: 0
              max_value: 100000
              severity: error
      - name: mrr_growth_pct
        tests:
          - dbt_utils.accepted_range:
              min_value: -1.0
              max_value: 0.5
              severity: warn
              config:
                where: "status = 'active'"
```

The `monthly_amount` test will catch a bug that sets subscription amounts to zero — a case that passes `not_null` cleanly. The `mrr_growth_pct` test uses `severity: warn` because growth above 50% month-over-month is unusual but not impossible; you want a flag in the logs, not a build failure.

### Category 2: Business rule tests

Some domain invariants cannot be expressed as range checks. They are rules: every active subscription must have a start date in the past; every cancelled subscription must have a cancellation date. These belong in custom generic tests.

```sql
-- tests/generic/assert_active_subscription_start_date_in_past.sql
{% test assert_active_subscription_start_date_in_past(model, column_name) %}

select
    {{ column_name }}
from {{ model }}
where status = 'active'
  and {{ column_name }} > current_date

{% endtest %}
```

Wire it up in the schema YAML alongside an explicit `accepted_values` list for status:

```yaml
# models/marts/schema.yml
models:
  - name: fct_subscriptions
    columns:
      - name: status
        tests:
          - accepted_values:
              values: ['active', 'cancelled', 'paused', 'trialing']
              severity: error
      - name: start_date
        tests:
          - assert_active_subscription_start_date_in_past
```

The `accepted_values` test on `status` is doing more work than it looks like here. If someone adds a `'suspended'` status upstream without updating the mart logic, this test fails immediately. Without the explicit list, `'suspended'` subscriptions flow silently into your active customer count.

### Category 3: Cross-model reconciliation tests

This is the category most projects skip entirely, and it is where the most expensive errors hide. The idea is simple: the same business metric calculated two different ways should produce the same result within a defined tolerance.

```sql
-- tests/assert_mrr_reconciles_to_invoices.sql
{% set tolerance_pct = 0.01 %}

with mrr_total as (
    select sum(mrr) as total
    from {{ ref('fct_mrr') }}
    where month_start = date_trunc('month', current_date - interval '1 month')
),

invoice_total as (
    select sum(amount) as total
    from {{ ref('stg_invoices') }}
    where status = 'paid'
      and invoice_date >= date_trunc('month', current_date - interval '1 month')
      and invoice_date < date_trunc('month', current_date)
),

comparison as (
    select
        mrr_total.total as mrr_sum,
        invoice_total.total as invoice_sum,
        abs(mrr_total.total - invoice_total.total) / nullif(invoice_total.total, 0) as diff_pct
    from mrr_total
    cross join invoice_total
)

select *
from comparison
where diff_pct > {{ tolerance_pct }}
```

This test catches the scenario that causes the most damage in practice: a new subscription type is added, the staging model picks it up, but the mart filter was not updated. The mart and the source diverge. Every downstream metric is wrong. The test fails on the first run after the gap appears, not three weeks later in a business review.

## What to prioritise

Not every column needs a business logic test. Prioritising is straightforward: start with anything that ends up in an executive dashboard or board report. That is the content where wrong numbers have the highest cost.

For revenue columns, the minimum bar is a range test plus a cross-model reconciliation. For status columns, an explicit `accepted_values` list rather than just `not_null`. For date columns on historical facts, a check that the value is not in the future.

```yaml
# models/marts/schema.yml — date sanity example
      - name: event_date
        tests:
          - not_null
          - dbt_utils.accepted_range:
              max_value: "cast(current_date as date)"
              severity: error
```

One production note worth taking seriously: use `severity: warn` for tests you want visibility on without failing the build, and `severity: error` only for tests that represent data you genuinely cannot trust downstream. If everything is `error`, teams start ignoring the red builds or disabling tests to get deploys through. Build fatigue is real, and a ignored test suite is worse than a small one.

The goal is a suite where a green build means something. Where the pass signal carries information. That requires being deliberate about what you test and how loudly each failure should ring.

<div class="takeaways">
<h2>Takeaways</h2>
<ul>
<li><strong>not_null and unique test infrastructure, not meaning</strong> — a column can pass both and contain values that are completely wrong from a business perspective.</li>
<li><strong>Range tests on financial columns catch silent zeroing bugs</strong> — use dbt_utils.accepted_range with realistic min/max values on any column that feeds a revenue metric.</li>
<li><strong>Explicit accepted_values lists are load-bearing</strong> — they fail immediately when a new status is added upstream without a corresponding update to mart logic, rather than silently polluting aggregates.</li>
<li><strong>Cross-model reconciliation tests catch the most expensive errors</strong> — comparing the same metric across two models flags divergence the moment it appears, not weeks later in a business review.</li>
<li><strong>Reserve severity: error for tests that represent genuinely untrustworthy data</strong> — overusing error severity causes build fatigue, which leads to disabled tests and no coverage at all.</li>
</ul>
</div>

---

What is the most expensive data error you have caught — or not caught in time — with a dbt test?
