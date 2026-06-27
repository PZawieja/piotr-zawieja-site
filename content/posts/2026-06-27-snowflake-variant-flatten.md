---
title: You've been flattening Snowflake JSON wrong
date: 2026-06-27
published_at: '2026-06-27T08:18:53Z'
slug: snowflake-variant-flatten
description: LATERAL FLATTEN is the wrong default for Snowflake JSON. Dot-notation,
  parsed columns, and when to actually flatten — with SQL for each.
tags:
- Snowflake
read_time: 9
status: published
---

A Salesforce webhook dumps events into Snowflake. They land in a VARIANT column called `payload`. Someone needs the account name out of it. Within ten minutes, this query exists in your codebase:

```sql
SELECT
      f.value:account_name::STRING AS account_name
FROM  raw.events,
LATERAL FLATTEN(INPUT => payload:records) f
```

It works in dev. On 10 million rows it takes four minutes. Six months later, half your warehouse credits come from JSON queries and nobody quite remembers why.

The problem isn't VARIANT. It's using `LATERAL FLATTEN` as a reflex when dot-notation would be faster, or parsing at load time would be better still. There are three tools for Snowflake JSON and most teams only reach for one of them.

---

## What VARIANT actually is

Think of a regular Snowflake column like a spreadsheet: every cell in a column holds the same kind of data — all integers, all timestamps. Snowflake stores each column as a compressed columnar block and builds statistics on it (min/max, distinct count). That's what makes typed column filters fast.

A VARIANT column is like a filing cabinet drawer where each slot holds whatever arrived. One row might have a flat JSON object with five keys. The next might have a nested object three levels deep. The one after might have an array of fifty items. No rules about shape.

Snowflake stores VARIANT as a compressed internal binary format, and it handles deep nesting without issues. The flexibility is real. But Snowflake can't build the same statistics on VARIANT data that it builds on typed columns — it doesn't know at planning time how many distinct values `payload:account_id` contains. That's the cost, and it shows up in query profiles.

<div class="callout callout-info">
<span class="callout-label">context</span>
<p>Snowflake VARIANT supports JSON, Avro, ORC, Parquet, and XML. In practice at analytics engineering shops, it's almost always JSON from webhooks, CDPs, CRMs, or product event streams. Everything here assumes JSON.</p>
</div>

---

## Tool 1: Dot-notation for scalar fields

When you need a single value from a JSON object — not an array, just a field — dot-notation is the right tool. It's fast, it reads clearly, and it doesn't require any joins or unnesting.

```sql
SELECT
      payload:event_type::STRING          AS event_type
    , payload:account_id::STRING          AS account_id
    , payload:amount::FLOAT               AS amount_usd
    , payload:customer.name::STRING       AS customer_name
    , payload:customer.address.city::STRING AS city
FROM  raw.webhook_events
WHERE payload:event_type::STRING = 'payment_completed'
```

Two things to know about this syntax:

**Colon accesses the field.** `payload:account_id` navigates into the VARIANT using the field name. For nested fields, dots go deeper: `payload:customer.address.city` descends three levels.

**Double-colon casts to a type.** `::STRING`, `::FLOAT`, `::INT`, `::BOOLEAN`, `::TIMESTAMP_NTZ` — always cast immediately. If you skip the cast, you get VARIANT back. Every downstream join and comparison on that result does implicit casting, which quietly hurts performance and can throw type mismatch errors on rows with unexpected shapes.

<div class="callout callout-tip">
<span class="callout-label">tip</span>
<p>Use <code>TRY_CAST</code> when the source JSON is dirty. <code>payload:amount::FLOAT</code> errors on the row if the value is <code>"N/A"</code>. <code>TRY_TO_DOUBLE(payload:amount)</code> returns NULL instead. For webhook data from external systems, TRY_ variants save a lot of pain.</p>
</div>

Dot-notation handles nested objects cleanly. What it can't handle is arrays — if `payload:line_items` is a JSON array, `payload:line_items::STRING` gives you the entire array serialised as a string, which isn't useful. That's where FLATTEN comes in.

---

## Tool 2: LATERAL FLATTEN for arrays

LATERAL FLATTEN exists to explode arrays into rows. It is the right tool when you genuinely have an array to unnest. It is the wrong tool when you're using it to reach a scalar field.

Here's the mental model: each row in your table is a bag of items. LATERAL FLATTEN reaches into each bag and pulls out every item as its own row. A bag with 3 items becomes 3 rows. A bag with 100 items becomes 100 rows.

```sql
-- One row per order before; one row per line item after
SELECT
      o.order_id
    , o.created_at
    , f.value:product_id::STRING  AS product_id
    , f.value:quantity::INT       AS quantity
    , f.value:unit_price::FLOAT   AS unit_price
FROM  raw.orders o
      , LATERAL FLATTEN(INPUT => o.payload:line_items) f
```

FLATTEN returns several columns from each expanded row — `SEQ`, `KEY`, `PATH`, `INDEX`, `VALUE`, `THIS`. For array elements, `f.value` is what you want: the actual array item. Use `f.index` when you need the position of the element within the array.

<div class="callout callout-warn">
<span class="callout-label">watch out</span>
<p>If a row has an empty array or a NULL in the array field, LATERAL FLATTEN silently drops that row from your result. You lose orders with no line items, users with no events, accounts with no contacts — without any error. Add <code>OUTER => TRUE</code> to keep those rows with NULLs: <code>LATERAL FLATTEN(INPUT => o.payload:line_items, OUTER => TRUE) f</code></p>
</div>

### The cardinality problem

This is where teams get into trouble with FLATTEN. A query that looks like "one row per order" now returns "one row per line item across all orders." If you then aggregate without realising this, you multiply counts, sums, and averages silently.

<div class="pull-quote">
LATERAL FLATTEN doesn't warn you that it multiplied your rows. The bug shows up in your aggregations two weeks later when the numbers don't match the source system.
</div>

Check expansion factor before using FLATTEN in a production model:

```sql
SELECT
      COUNT(*)                              AS orders
    , SUM(ARRAY_SIZE(payload:line_items))   AS total_line_items
    , AVG(ARRAY_SIZE(payload:line_items))   AS avg_per_order
    , MAX(ARRAY_SIZE(payload:line_items))   AS max_per_order
FROM  raw.orders
```

If `max_per_order` is 300 and you have 10 million orders, your flattened result set could be hundreds of millions of rows. Know this before you build a model on top of it.

### FLATTEN for key-value objects

FLATTEN also handles the case where you have a JSON object with unknown or variable keys and you need to pivot it long. Use `f.key` to get the field name and `f.value` to get the value:

```sql
-- Explode {"clicks": 4, "opens": 12, "bounces": 0} into rows
SELECT
      email_id
    , f.key::STRING   AS metric_name
    , f.value::INT    AS metric_value
FROM  raw.email_events
      , LATERAL FLATTEN(INPUT => payload:metrics) f
```

This is legitimate use of FLATTEN on an object (not an array). The same cardinality warning applies — each key-value pair becomes a row.

---

## Tool 3: Parse at load time

When the JSON schema is stable and you query the same fields over and over, the best approach is to parse once in your staging model and never touch VARIANT again downstream.

```sql
-- models/staging/stg_webhook_events.sql
SELECT
      event_id
    , event_type
    , occurred_at
    , raw_payload:account_id::STRING       AS account_id
    , raw_payload:amount::FLOAT            AS amount_usd
    , raw_payload:currency::STRING         AS currency
    , raw_payload:customer.name::STRING    AS customer_name
    , raw_payload:customer.email::STRING   AS customer_email
    , raw_payload                          AS _raw_payload
FROM  {{ source('webhook', 'raw_events') }}
```

After this model, every downstream model works with typed columns. No VARIANT access, no FLATTEN, no casting in production queries. The staging model pays the parsing cost once; everything downstream is a fast typed-column scan.

Keep `_raw_payload` in staging. When the source system adds new fields six months from now, you can backfill them from `_raw_payload` without re-ingesting source data. This has saved every team I've worked on at least one painful backfill.

<div class="callout callout-tip">
<span class="callout-label">tip</span>
<p>For array columns that you'll need to unnest frequently, consider a separate staging model specifically for the flattened version — <code>stg_orders__line_items</code> alongside <code>stg_orders</code>. Centralise the FLATTEN once, test the cardinality in that model, and let everything else join to the already-flat table.</p>
</div>

---

## Choosing the right tool

<div class="decision-tree">
<p class="decision-tree-title">Which VARIANT access pattern to use</p>
<div class="decision-step">
  <span class="decision-q">Stable JSON schema, same fields queried repeatedly</span>
  <span class="decision-a"><strong>Parse at load</strong> in your staging model. Typed columns from that point forward.</span>
</div>
<div class="decision-step">
  <span class="decision-q">Ad-hoc scalar field from a JSON object</span>
  <span class="decision-a"><strong>Dot-notation</strong> with immediate type cast. Works in any SELECT without joins.</span>
</div>
<div class="decision-step">
  <span class="decision-q">Array that needs to become rows</span>
  <span class="decision-a"><strong>LATERAL FLATTEN</strong> with OUTER => TRUE. Check expansion factor first.</span>
</div>
<div class="decision-step">
  <span class="decision-q">Variable-key JSON object, need all keys as rows</span>
  <span class="decision-a"><strong>LATERAL FLATTEN</strong> using f.key and f.value. Same cardinality warning applies.</span>
</div>
</div>

---

## Side by side

<div class="tradeoff-grid">
<div class="tradeoff-row header">
  <span class="tradeoff-cell">Approach</span>
  <span class="tradeoff-cell">Best for</span>
  <span class="tradeoff-cell">Performance</span>
  <span class="tradeoff-cell">Main risk</span>
</div>
<div class="tradeoff-row">
  <span class="tradeoff-cell">Parse at load (typed columns)</span>
  <span class="tradeoff-cell">Stable schema, repeated queries</span>
  <span class="tradeoff-cell">Fastest — no VARIANT at query time</span>
  <span class="tradeoff-cell">Schema changes need a model update</span>
</div>
<div class="tradeoff-row">
  <span class="tradeoff-cell">Dot-notation</span>
  <span class="tradeoff-cell">Scalar fields, ad-hoc access</span>
  <span class="tradeoff-cell">Good — Snowflake optimises path access</span>
  <span class="tradeoff-cell">Forgetting ::TYPE → implicit casting downstream</span>
</div>
<div class="tradeoff-row">
  <span class="tradeoff-cell">LATERAL FLATTEN</span>
  <span class="tradeoff-cell">Arrays and key-value pivots</span>
  <span class="tradeoff-cell">Expensive — row multiplication at scale</span>
  <span class="tradeoff-cell">Silent cardinality explosion in aggregations</span>
</div>
</div>

The default in most teams is: JSON arrives → VARIANT → LATERAL FLATTEN everything. The correct default is the reverse: parse scalars at load time, use dot-notation for ad-hoc access, and reach for FLATTEN only when you have an actual array that needs to become rows.

VARIANT is not the problem. FLATTEN as a reflex is.

<div class="takeaways">
<h2>Takeaways</h2>
<ul>
<li><strong>LATERAL FLATTEN is for arrays, not JSON in general</strong> — if you're reading a scalar field, dot-notation is faster and doesn't multiply your rows.</li>
<li><strong>Always cast with ::TYPE immediately</strong> — leaving results as VARIANT propagates implicit casting through every downstream query and causes hard-to-debug type errors.</li>
<li><strong>OUTER => TRUE keeps rows with empty or null arrays</strong> — without it, those rows silently disappear from your result.</li>
<li><strong>Check expansion factor before FLATTENing in production</strong> — <code>MAX(ARRAY_SIZE(col))</code> tells you how much your row count multiplies.</li>
<li><strong>Stable schema? Parse in staging, never touch VARIANT downstream</strong> — typed columns are always faster than VARIANT path access at query time.</li>
<li><strong>Keep _raw_payload in your staging model</strong> — when the source system adds new fields later, you can backfill without re-ingesting.</li>
</ul>
</div>

Which JSON pattern has cost you the most — cardinality explosions from FLATTEN, type casting bugs on dirty payloads, or schema drift from the source system silently breaking your queries?