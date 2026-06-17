---
title: 'Snowflake clustering keys: what they are, when they help, and when to skip
  them'
date: 2026-06-16
published_at: '2026-06-16T18:27:14Z'
slug: snowflake-clustering-keys-guide
description: Clustering keys improve query performance by rearranging micro-partitions
  — but they cost credits continuously. Here is when the trade-off is worth it.
tags:
- Snowflake
read_time: 10
status: published
---

Your Snowflake UI recommended adding a clustering key to a large events table. You did. One dashboard query went from 45 seconds to 12. Then your credit bill came in and compute costs were up 18% for the month.

Was it worth it? The answer requires understanding what clustering keys actually do — and what they keep doing, every time you load new data. Snowflake had, technically, done exactly what you asked. That's almost worse.

---

## How Snowflake stores data

Snowflake stores table data in **micro-partitions**: immutable, compressed files of roughly 50–500 MB of uncompressed data each. Every time you load data, Snowflake writes new micro-partitions in the order the rows arrive.

Alongside each micro-partition, Snowflake stores metadata: for every column, the minimum and maximum value in that partition. This is what makes pruning possible. When a query runs `WHERE event_date = '2026-05-01'`, Snowflake checks the metadata for all micro-partitions and skips any partition whose `event_date` range doesn't include that date — without reading the partition itself.

This metadata-driven pruning is the core of Snowflake's performance model. Clustering keys only matter insofar as they improve it.

In plain English: imagine a supermarket where the stock boy shelves whatever arrives wherever there's free space — milk next to motor oil, bread next to batteries. You can still find what you need, you just have to check every aisle. A clustering key is reorganizing the store by category, so dairy is always together — once you know to look in the dairy aisle, you skip the rest of the store entirely. That's pruning. But somebody has to keep re-shelving the store every time a delivery truck arrives, and nobody enjoys doing that at 2am — least of all your credit bill.

**Natural clustering** is what you get for free. When you bulk-load an events table one day at a time, data for each day lands in a small number of micro-partitions with a narrow date range. Queries filtering on that date will prune well without any explicit clustering. When you load from a CDC feed or backfill historical data, rows for many different dates get mixed into the same micro-partitions, pruning degrades, and queries slow down.

---

## What a clustering key changes

A clustering key tells Snowflake to keep rows with similar values for the key column(s) co-located in the same micro-partitions. Snowflake's **Automatic Clustering** service — separate from your query warehouses — does this work in the background, rearranging data after loads to maintain good clustering depth.

```sql
ALTER TABLE events CLUSTER BY (event_date);
```

After this, Snowflake continuously monitors the table. When new data loads and degrades the clustering, the service re-sorts affected data into new micro-partitions. A query filtering on `event_date` now finds far fewer overlapping partitions to read.

The cost: the clustering service runs on serverless compute and charges credits whenever it reclusters. Those credits are charged to your account separately from your query warehouses. On a high-write table, this is not a one-time cost — it is ongoing.

---

## Measuring clustering health before deciding

Never add a clustering key without first measuring whether clustering is actually the problem. The function to use:

```sql
SELECT SYSTEM$CLUSTERING_INFORMATION('events', '(event_date)');
```

This returns JSON. The two numbers that matter:

- **`average_overlaps`**: how many other micro-partitions overlap in range with a typical micro-partition. A value near 0 means good clustering — most micro-partitions have a narrow, non-overlapping range. A value of 50 means any given partition's range overlaps with 50 others, so a point lookup scans 51 partitions instead of 1.
- **`average_depth`**: the average number of micro-partitions that must be scanned to find all rows for a single value. Depth of 1 is perfect. Depth of 20 means your query is scanning 20× more data than necessary.

```sql
-- Run this before and after adding a clustering key
SELECT
    PARSE_JSON(
        SYSTEM$CLUSTERING_INFORMATION('events', '(event_date)')
    )['average_overlaps']::FLOAT AS avg_overlaps,
    PARSE_JSON(
        SYSTEM$CLUSTERING_INFORMATION('events', '(event_date)')
    )['average_depth']::FLOAT    AS avg_depth;
```

If `average_depth` is already close to 1, your data is naturally well-clustered on that column. Adding an explicit clustering key will achieve nothing except an ongoing credit cost.

---

## When clustering earns its cost

**Table is large and data arrives out of natural order.** The threshold where clustering becomes meaningful is roughly 500 GB of uncompressed data (Snowflake's own documentation suggests 1 TB, but degraded clustering on a 500 GB table can be measurable). Below that, full table scans are fast enough that pruning improvement doesn't matter.

For tables over 1 TB where `SYSTEM$CLUSTERING_INFORMATION` shows `average_depth` above 10, explicit clustering will meaningfully reduce bytes scanned on filtered queries.

**Queries consistently filter on the same column.** A clustering key is a bet: you pay to co-locate data by one dimension so that queries filtering on that dimension scan less. If 80% of your queries filter on `event_date`, clustering on `event_date` is a good bet. If queries filter on `event_date`, `customer_id`, `product_id`, and `region` roughly equally, no single clustering key satisfies them all — you are paying credits to help one query pattern while doing nothing for the others.

**Recency queries on an append-only table with backfill.** The hardest case for natural clustering. You have a 2 TB events table where you frequently backfill late-arriving events from 30 days ago. Every backfill load scatters old-date rows across new micro-partitions. `SYSTEM$CLUSTERING_INFORMATION` will show high overlap on `event_date`. This is exactly where explicit clustering pays off.

---

## When to skip it

**The table is under 500 GB.** At this size, Snowflake's full scan is fast enough that pruning improvement rarely justifies the continuous reclustering cost. Use a larger warehouse instead — it is cheaper per query and has no ongoing overhead.

**Write rates are high.** If the table receives continuous small loads — streaming inserts, Fivetran syncs every 5 minutes, Kafka connectors — the clustering service will trigger frequently. On a 1 TB table with hourly loads, this can cost more credits than the query savings recover. Use `SYSTEM$ESTIMATE_AUTOMATIC_CLUSTERING_CREDITS` to check before committing. The function requires a clustering key to already be defined, so the practical workflow is: add the key, suspend reclustering immediately, estimate, then decide.

```sql
ALTER TABLE events CLUSTER BY (event_date);
ALTER TABLE events SUSPEND RECLUSTER;

SELECT SYSTEM$ESTIMATE_AUTOMATIC_CLUSTERING_CREDITS('events');
```

If the estimate is higher than what you're currently spending on queries against this table (visible in `QUERY_HISTORY`), drop the key: `ALTER TABLE events DROP CLUSTERING KEY`.

**Low-cardinality columns.** Clustering on a boolean column or a column with 5 distinct values doesn't help. Each micro-partition will still contain a wide value range. It's like sorting a parking lot into "has a roof" and "doesn't" — half the lot still matches whichever one you pick, so you've organized nothing. Use `accepted_values` tests for those columns instead and forget about clustering.

**The table already has good natural clustering.** If data is loaded in chronological order and queries filter on the load timestamp or date, the natural insertion order provides good clustering for free. Verify with `SYSTEM$CLUSTERING_INFORMATION` — if `average_depth` is already under 3, leave it alone.

---

<div class="decision-tree">
<p class="decision-tree-title">Decision Tree</p>
<div class="decision-step">
<span class="decision-q">If `average_depth` < 5</span>
<span class="decision-a">Skip clustering — your data is already well-organized; an explicit key buys nothing.</span>
</div>
<div class="decision-step">
<span class="decision-q">If the table is under 500 GB</span>
<span class="decision-a">Skip clustering — use a bigger warehouse for the occasional slow query instead. Cheaper, no ongoing cost.</span>
</div>
<div class="decision-step">
<span class="decision-q">If queries filter on many different columns about equally</span>
<span class="decision-a">Skip clustering — no single key serves all of them; you'd pay for one pattern while ignoring the rest.</span>
</div>
<div class="decision-step">
<span class="decision-q">If the table is over 1 TB, `average_depth` > 10, and most queries filter the same column</span>
<span class="decision-a">Add the <strong>clustering key</strong> on that column — this is the case it's actually built for.</span>
</div>
<div class="decision-step">
<span class="decision-q">If writes are frequent (streaming, Kafka, 5-minute syncs)</span>
<span class="decision-a">Run `SYSTEM$ESTIMATE_AUTOMATIC_CLUSTERING_CREDITS` before committing — high write rates can make reclustering cost more than it saves.</span>
</div>
<div class="decision-step">
<span class="decision-q">If you're about to run a bulk load</span>
<span class="decision-a">`SUSPEND RECLUSTER` first, load, then `RESUME RECLUSTER` — don't pay to recluster mid-batch.</span>
</div>
</div>

---

## The cost model for Automatic Clustering

Once you add a clustering key, Snowflake runs Automatic Clustering continuously. The cost is:

1. **Initial reclustering**: when you first add the key, Snowflake rearranges the entire table. For a 1 TB table this can be significant — run it during low-traffic hours and watch the credit meter.
2. **Ongoing maintenance**: every time new data loads and degrades clustering, the service reclusters the affected micro-partitions. Cost scales with write volume, not just table size.

You can pause clustering if you need to temporarily suspend costs or are running a bulk load:

```sql
ALTER TABLE events SUSPEND RECLUSTER;

-- run bulk load

ALTER TABLE events RESUME RECLUSTER;
```

During `SUSPEND RECLUSTER`, new data loads without triggering the clustering service. Clustering depth will degrade. Resume when the load is complete and clustering will catch up.

---

## Using clustering keys with dbt

dbt exposes Snowflake clustering through the `cluster_by` config on `table` and `incremental` materializations:

```sql
{{ config(
    materialized='incremental',
    unique_key='event_id',
    cluster_by=['event_date']
) }}

SELECT
    event_id,
    event_date,
    user_id,
    event_type,
    revenue
FROM {{ source('events', 'raw_events') }}
{% if is_incremental() %}
    WHERE event_date >= (SELECT MAX(event_date) FROM {{ this }})
{% endif %}
```

For `incremental` materializations, dbt applies `ALTER TABLE ... CLUSTER BY` after the initial table creation. For `table` materializations, the key is included in the `CREATE OR REPLACE TABLE` DDL directly. Either way, Automatic Clustering takes over once the key is set.

One caution: `cluster_by` on an `incremental` model doesn't undo poor natural clustering that accumulated before you added it. If you add clustering to an existing large incremental model, verify with `SYSTEM$CLUSTERING_INFORMATION` that depth actually improves — the initial recluster of a large table can take time.

For `table` materializations, dbt rebuilds the table from scratch on every run. The rebuild produces naturally ordered micro-partitions from the query result, so clustering is implicitly reset each run. Adding `cluster_by` on a `table` materialization rarely has measurable impact unless the query itself produces non-ordered output for the key column.

---

## The decision checklist

Before adding a clustering key to any table:

1. Run `SYSTEM$CLUSTERING_INFORMATION` — if `average_depth` < 5, stop here.
2. Confirm the table is > 500 GB uncompressed.
3. Confirm > 60% of expensive queries filter on the same column(s).
4. Run `SYSTEM$ESTIMATE_AUTOMATIC_CLUSTERING_CREDITS` — compare against current query spend on this table.
5. Add the key, let it recluster, measure `average_depth` again and run the same queries with `ALTER SESSION SET USE_CACHED_RESULT = FALSE`.
6. If query improvement doesn't justify the ongoing credit cost, drop the key with `ALTER TABLE events DROP CLUSTERING KEY` — no data is lost, only the clustering metadata.

Clustering keys are easy to add and easy to remove. The mistake is adding them reflexively and never checking whether the spend is justified.

<div class="takeaways">
<h2>Takeaways</h2>
<ul>
<li><strong>Clustering keys improve micro-partition pruning — but cost credits continuously</strong> — the Automatic Clustering service reclusters data after every load, as an ongoing charge separate from your query warehouses.</li>
<li><strong>Measure first with SYSTEM$CLUSTERING_INFORMATION</strong> — if <code>average_depth</code> is already under 5, your data is naturally well-clustered and an explicit key will cost money for no gain.</li>
<li><strong>The table needs to be large to justify clustering</strong> — under 500 GB, full scans are fast enough that pruning improvement doesn't recover the reclustering cost.</li>
<li><strong>A clustering key is a bet on one query pattern</strong> — if your queries filter on multiple different columns, no single key helps all of them; you pay for one and leave the others unchanged.</li>
<li><strong>Estimate the ongoing cost before committing</strong> — <code>SYSTEM$ESTIMATE_AUTOMATIC_CLUSTERING_CREDITS</code> gives you the credit forecast; compare it against actual query spend on the table before proceeding.</li>
<li><strong>Use SUSPEND/RESUME RECLUSTER around bulk loads</strong> — triggering reclustering on every batch in a large bulk load is expensive; suspend, load, then let the service catch up once.</li>
</ul>
</div>

How many clustering keys in your Snowflake account were added speculatively and never had their credit cost checked?