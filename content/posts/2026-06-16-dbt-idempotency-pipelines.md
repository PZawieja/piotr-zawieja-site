---
title: 'Idempotency in dbt: the one pipeline property worth obsessing over'
date: 2026-06-16
published_at: '2026-06-16T08:05:07Z'
slug: dbt-idempotency-pipelines
description: Most dbt models look idempotent but aren't. What breaks it silently and
  the concrete patterns — unique_key, surrogate keys, partition replacement — that
  fix it.
tags:
- dbt
read_time: 8
status: published
---

You re-ran the pipeline last night because a source table was late. This morning, Finance is asking why revenue is 12% higher than yesterday's close. Your incremental model ran twice on the same data. The numbers are wrong. The pipeline passed all tests.

This is an idempotency failure. It is the most common silent bug in dbt projects, and it is almost never caught by dbt tests because tests run on the current state, not across multiple runs.

Idempotency means: running the same pipeline multiple times with the same inputs produces the same output as running it once. An idempotent model can be re-run after a failure, a backfill, or an accidental double-trigger, and the result is always correct. A non-idempotent model can't make that promise.

---

## Why dbt makes this easy to get wrong

dbt has two common materialization modes: `table` and `incremental`. Tables are always idempotent — they rebuild from scratch on every run. Incremental models are not idempotent by default, and that is where most problems live.

The core issue: incremental models accumulate rows. Without an explicit deduplication strategy, running the same source data twice appends it twice.

```sql
{{ config(materialized='incremental') }}

SELECT
    order_id,
    customer_id,
    order_date,
    revenue
FROM {{ source('ecommerce', 'orders') }}
{% if is_incremental() %}
    WHERE order_date >= (SELECT MAX(order_date) FROM {{ this }})
{% endif %}
```

This model has three idempotency problems. The `WHERE` clause uses `MAX(order_date)` from the target table — if a run fails midway, or if source data lands late for a date already past the watermark, re-running will either duplicate rows or silently drop late-arriving records. A forced re-run after a bug fix repulls everything and appends it all again.

---

## Four patterns that break idempotency

### Watermark-based filtering without deduplication

The most common pattern. The model filters new rows using the maximum timestamp or date from the target table. This works only if every source row arrives exactly once, the source never updates existing rows, and runs never overlap.

In practice, none of those hold consistently. Source tables get corrected. Pipelines get retriggered. Late data arrives. The watermark approach gives you the appearance of an incremental strategy without the safety.

### Append-only incrementals with no unique_key

dbt's `unique_key` config triggers a merge or upsert instead of a plain append. Without it, every incremental run adds rows unconditionally.

```sql
-- Appends unconditionally — running twice doubles the rows
{{ config(materialized='incremental') }}

-- Upserts on order_id — running twice is safe
{{ config(
    materialized='incremental',
    unique_key='order_id'
) }}
```

The difference is one config line. Most projects start without `unique_key` and add it only after the first incident.

### Non-deterministic column values

Columns whose values change between runs break idempotency even when the source data is identical.

```sql
SELECT
    order_id,
    revenue,
    CURRENT_TIMESTAMP() AS loaded_at
FROM {{ source('ecommerce', 'orders') }}
```

`loaded_at` populated with `CURRENT_TIMESTAMP()` is a common offender. So is `SYSDATE()` or `NOW()`. If your merge key doesn't include this column, duplicate rows accumulate. If it does, rows that haven't changed get updated unnecessarily, complicating change detection downstream.

Fix: use a deterministic timestamp from the source data itself — `updated_at`, `created_at`, or `_fivetran_synced` — never from the pipeline execution clock.

### Row-order dependencies

Models using `ROW_NUMBER()` or `RANK()` without a fully deterministic `ORDER BY` can produce different results across runs if the warehouse doesn't guarantee source ordering.

```sql
-- Non-deterministic when created_at has ties
SELECT
    *,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY created_at
    ) AS row_num
FROM orders
```

When `created_at` has ties, which row gets rank 1 is arbitrary and may differ between runs on Snowflake virtual warehouses with different node counts. Always add a tiebreaker — a source-provided ID or surrogate key — to make the ordering deterministic.

---

## The patterns that restore idempotency

### unique_key with merge strategy

Set `unique_key` on every incremental model. This is the single highest-leverage change in a dbt project for idempotency.

```sql
{{ config(
    materialized='incremental',
    unique_key='order_id',
    incremental_strategy='merge'
) }}

SELECT
    order_id,
    customer_id,
    order_date,
    revenue,
    updated_at
FROM {{ source('ecommerce', 'orders') }}
{% if is_incremental() %}
    WHERE updated_at > (SELECT MAX(updated_at) FROM {{ this }})
{% endif %}
```

With `unique_key`, if a row with the same `order_id` already exists in the target, it gets updated rather than duplicated. Re-running is safe regardless of how many times the pipeline triggers.

`incremental_strategy='merge'` is supported on Snowflake, BigQuery, and Databricks. On Postgres and Redshift, dbt uses delete+insert instead, which is equally safe from an idempotency standpoint.

### Surrogate keys for composite natural keys

When the natural key is composite, define a surrogate key in staging rather than passing a multi-column tuple as `unique_key`. The `generate_surrogate_key()` macro from `dbt-utils` handles this cleanly:

```sql
-- models/staging/stg_order_lines.sql
SELECT
    {{ dbt_utils.generate_surrogate_key(['order_id', 'line_item_id']) }} AS order_line_sk,
    order_id,
    line_item_id,
    quantity,
    unit_price,
    line_total
FROM {{ source('ecommerce', 'order_lines') }}
```

Then the incremental model merges on one column:

```sql
{{ config(
    materialized='incremental',
    unique_key='order_line_sk'
) }}

SELECT *
FROM {{ ref('stg_order_lines') }}
{% if is_incremental() %}
    WHERE updated_at > (SELECT MAX(updated_at) FROM {{ this }})
{% endif %}
```

One deterministic column, safe to merge on, easy to test with a `unique` test on the staging model.

### Partition replacement for large fact tables

For large event or transaction tables where a full merge is expensive, partition replacement gives you idempotency at partition granularity. The entire partition is replaced atomically on each run.

On BigQuery:

```sql
{{ config(
    materialized='incremental',
    incremental_strategy='insert_overwrite',
    partition_by={
        'field': 'event_date',
        'data_type': 'date'
    }
) }}

SELECT
    event_id,
    event_date,
    user_id,
    event_type
FROM {{ source('analytics', 'events') }}
{% if is_incremental() %}
    WHERE event_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 3 DAY)
{% endif %}
```

Re-running this always produces the same partition contents for the last 3 days. Late-arriving records and source corrections are handled automatically. The tradeoff: you reprocess 3 days of data on every run, which is more than a pure incremental but far less than a full refresh.

On Snowflake, `incremental_strategy='delete+insert'` with a `unique_key` achieves the same effect — it deletes matching rows in the target partition and reinserts the current version.

### Wrapping all incremental filters in is_incremental()

`is_incremental()` evaluates to `false` on a `--full-refresh` run. This is your escape hatch when you need to rebuild from scratch after a bug fix or data correction.

The rule: every filter that scopes data to the current increment must live inside `{% if is_incremental() %}`. A filter outside this block runs even on full refresh, silently truncating history.

```sql
-- Wrong: the hard-coded date cutoff applies even on full-refresh
SELECT *
FROM {{ source('ecommerce', 'orders') }}
WHERE order_date >= '2026-01-01'
{% if is_incremental() %}
    AND updated_at > (SELECT MAX(updated_at) FROM {{ this }})
{% endif %}
```

```sql
-- Correct: all incremental scoping is inside the block
SELECT *
FROM {{ source('ecommerce', 'orders') }}
{% if is_incremental() %}
    WHERE updated_at > (SELECT MAX(updated_at) FROM {{ this }})
{% endif %}
```

The first version will silently drop all pre-2026 history every time someone runs `dbt run --full-refresh`.

---

## How to test idempotency

dbt's built-in tests — `unique`, `not_null`, `relationships` — run on the current state of a model. They verify the state is correct after one run. They don't verify that a second run leaves the state unchanged.

The manual test is simple:

1. Run `dbt run --select <model>`
2. Record the row count: `SELECT COUNT(*) FROM <schema>.<model>`
3. Run `dbt run --select <model>` again without `--full-refresh`
4. Record the row count again

If the count increased, the model is not idempotent. Do this for every new incremental model before it reaches production.

For models that update existing rows, also check for duplicates:

```sql
SELECT
    order_id,
    COUNT(*) AS n
FROM fct_orders
GROUP BY order_id
HAVING n > 1
```

This should always return zero rows. If it returns rows after any re-run, your `unique_key` isn't covering all the paths by which duplicate source data can arrive.

A more durable approach is a singular test that materializes the model twice against a fixed seed or source and asserts the outputs are identical. More setup, but it becomes a permanent regression guard that runs in CI.

<div class="takeaways">
<h2>Takeaways</h2>
<ul>
<li><strong>Table materializations are idempotent by default — incremental models are not</strong> — every incremental model needs an explicit deduplication strategy, not just a watermark filter.</li>
<li><strong>unique_key is the highest-leverage single change</strong> — it converts append semantics to upsert semantics and makes re-runs safe without changing anything else about the model logic.</li>
<li><strong>Never use CURRENT_TIMESTAMP() in incremental logic</strong> — use source-provided timestamps; execution-time values create non-determinism that compounds across re-runs.</li>
<li><strong>Partition replacement trades compute for safety</strong> — replacing the last N partitions on every run is more expensive than a pure incremental but fully safe to re-run and handles late data naturally.</li>
<li><strong>Every incremental filter must live inside is_incremental()</strong> — a filter outside the block silently drops historical data on full refresh.</li>
<li><strong>Test idempotency by running twice</strong> — built-in dbt tests do not catch this; a second run with a row count comparison is the only reliable check.</li>
</ul>
</div>

How many of your incremental models could you re-run right now without checking the row counts afterward?