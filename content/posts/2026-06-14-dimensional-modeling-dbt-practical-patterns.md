---
date: 2026-06-14
description: Kimball tells you what to build, dbt gives you the tools. Where SCD Type 2 snapshots, bridge tables, and role-playing dimensions actually live.
published_at: '2026-06-14T12:19:51Z'
read_time: 9
slug: dimensional-modeling-dbt-practical-patterns
status: published
tags: [dbt]
title: 'Dimensional modeling in dbt: the patterns that don''t fit the textbook'
---

The textbook version of dimensional modeling is clean. Fact tables at the center, dimension tables surrounding them, foreign keys connecting them, surrogate keys disambiguating natural keys from different source systems. Every row in `fct_orders` points to a row in `dim_customer`, `dim_product`, `dim_date`. Star schema. Done.

Reality is messier. Customers change their email address. Products move between categories. The same date dimension needs to be referenced three times on the same fact table for order date, ship date, and return date. Orders can have multiple promotional codes.

dbt gives you the primitives to handle all of this, but the documentation mostly covers the clean cases. This post covers the patterns that show up in real projects — where the textbook diagram and the actual data don't quite match.

---

## SCD Type 2: use dbt snapshots, not incremental models

Slowly changing dimensions are the most common place teams reach for an incremental model and get it wrong. The instinct is understandable — incremental models process new and changed data, which sounds exactly right. But a merge incremental model will simply overwrite the old value with the new one. You lose history.

Type 2 slowly changing dimensions require a different approach: when a dimension attribute changes, close the existing record and open a new one. The dimension table carries all versions of the record, each with a validity window. This is what `dbt snapshot` is built for.

```sql
-- snapshots/snap_customers.sql
{% snapshot snap_customers %}

{{
    config(
        target_schema='snapshots',
        strategy='updated_at',
        unique_key='customer_id',
        updated_at='updated_at',
        invalidate_hard_deletes=True
    )
}}

SELECT
      customer_id
    , email
    , plan
    , country
    , updated_at
FROM {{ source('app', 'customers') }}

{% endsnapshot %}
```

The `strategy='updated_at'` tells dbt to check for changes by comparing the `updated_at` column. On each run, if `updated_at` has advanced for a given `customer_id`, dbt closes the current record (sets `dbt_valid_to` to the current timestamp) and inserts a new open record (with `dbt_valid_to` as NULL).

The alternative strategy is `check`:

```sql
{{
    config(
        strategy='check',
        check_cols=['email', 'plan', 'country'],
        unique_key='customer_id'
    )
}}
```

`check` compares the listed columns directly rather than relying on an `updated_at` column. Slower on large tables — it hashes the column values — but necessary when the source doesn't provide a reliable updated timestamp.

---

## Querying snapshots correctly

The snapshot creates a history table. Most downstream consumers want either current state or point-in-time state, and the query patterns are different.

**Current state** — all records where the validity window is still open:

```sql
-- models/marts/dim_customers.sql
SELECT
      customer_id
    , email
    , plan
    , country
    , dbt_valid_from  AS effective_from
FROM {{ ref('snap_customers') }}
WHERE dbt_valid_to IS NULL
```

**Point-in-time state** — the record that was current as of a given fact event:

```sql
-- models/intermediate/int_orders_with_customer_at_order_date.sql
SELECT
      o.order_id
    , o.customer_id
    , o.ordered_at
    , c.plan     AS customer_plan_at_order
    , c.country  AS customer_country_at_order
FROM {{ ref('fct_orders') }} o
LEFT JOIN {{ ref('snap_customers') }} c
    ON  o.customer_id  = c.customer_id
    AND o.ordered_at  >= c.dbt_valid_from
    AND (o.ordered_at  < c.dbt_valid_to OR c.dbt_valid_to IS NULL)
```

This join pattern — matching on the entity key and filtering where the fact timestamp falls within the validity window — is the fundamental one for any historical analysis that needs to know what a dimension looked like at the time of a fact event. Customer plan at the time of purchase. Product price at the time of the transaction. Account tier at the time of a support ticket.

---

## Degenerate dimensions

A degenerate dimension is a dimension attribute that lives on the fact table rather than in a separate dimension table. The most common example is `order_id` on a line item fact.

The line item fact is at the product-per-order grain:

```sql
-- models/marts/fct_order_lines.sql
SELECT
      {{ dbt_utils.generate_surrogate_key(['order_id', 'product_id']) }} AS order_line_id
    , order_id       -- degenerate dimension
    , product_id
    , customer_id
    , ordered_at
    , quantity
    , unit_price
    , quantity * unit_price  AS line_total
FROM {{ ref('stg_order_lines') }}
```

`order_id` is a degenerate dimension. There is no separate `dim_orders` table — the order itself has no attributes beyond those that already belong to the line items or to the customer. The order identifier lives directly on the fact row.

When should you promote a degenerate dimension to a full dimension table? When the "header" entity starts acquiring attributes that don't belong on the line. If orders have shipping addresses, discount codes, channel sources, and fulfillment statuses — those are order-level attributes that warrant a `dim_orders` table. If an order is nothing more than a grouping key for line items, keep it degenerate.

---

## Role-playing dimensions

`dim_date` typically appears once in a star schema diagram. In practice it appears three or four times on the same fact table.

```sql
-- models/marts/fct_orders.sql
SELECT
      order_id
    , customer_id
    , product_id

    , ordered_at::DATE    AS order_date_key
    , shipped_at::DATE    AS ship_date_key
    , returned_at::DATE   AS return_date_key

    , quantity
    , revenue
FROM {{ ref('stg_orders') }}
```

Each date key is a foreign key to `dim_date`, but playing a different role. In your BI tool, `order_date_key` joins to `dim_date` aliased as "Order Date", `ship_date_key` to the same table aliased as "Ship Date". The dimension is the same; the roles differ.

dbt doesn't need to do anything special here — you store the keys on the fact table and the joins happen in the BI layer. What you do need is clarity in your schema YAML about what each key represents:

```yaml
# models/marts/schema.yml
models:
  - name: fct_orders
    columns:
      - name: order_date_key
        description: "Date the order was placed. Foreign key to dim_date."
        tests:
          - not_null
          - relationships:
              to: ref('dim_date')
              field: date_key
      - name: ship_date_key
        description: "Date the order shipped. Null if not yet shipped."
        tests:
          - relationships:
              to: ref('dim_date')
              field: date_key
```

The `relationships` test on `ship_date_key` does not include `not_null` — unshipped orders legitimately have a null ship date. This is correct behavior, not a data quality issue.

---

## Bridge tables

A fact row relates to exactly one customer, one product, one date — that's the standard case. Bridge tables handle the exception: when a fact or dimension relates to multiple members of another dimension.

Common examples:
- A customer with multiple tags or segments
- A product in multiple categories
- An order with multiple applied promotions

The bridge table is a narrow join table at the relationship grain:

```sql
-- models/marts/brd_customer_tags.sql
SELECT
      customer_id
    , tag_id
    , tagged_at
FROM {{ ref('stg_customer_tags') }}
```

Querying through the bridge introduces fanout risk — if a customer has five tags and you join `fct_orders` to `brd_customer_tags`, each order row duplicates five times. Handle this deliberately:

```sql
-- Option A: aggregate before joining (preserves fact grain)
WITH customer_tag_list AS (
    SELECT
          customer_id
        , ARRAY_AGG(tag_id ORDER BY tagged_at) AS tags
    FROM {{ ref('brd_customer_tags') }}
    GROUP BY 1
)

SELECT
      o.order_id
    , o.revenue
    , t.tags
FROM {{ ref('fct_orders') }} o
LEFT JOIN customer_tag_list t USING (customer_id)


-- Option B: filter to one tag before joining (intentionally changes grain)
SELECT
      o.order_id
    , o.revenue
FROM {{ ref('fct_orders') }} o
INNER JOIN {{ ref('brd_customer_tags') }} t
    ON  o.customer_id = t.customer_id
    AND t.tag_id = 'enterprise'
```

Option A preserves the fact grain and returns all tags as an array. Option B intentionally scopes to a subset — only orders from enterprise-tagged customers. Both are valid; the choice depends on what the downstream consumer needs.

---

## When to skip dimensional modeling

Dimensional modeling is the right default for analytical data products with multiple downstream consumers and evolving query patterns. It is not the right default for everything.

A single-purpose dashboard with three metrics and one analyst querying it may not need a `dim_customer` and a `fct_orders` with a surrogate key and a bridge table for tags. A wide mart — one row per customer, all the attributes you care about as columns — is simpler, faster to build, and easier to debug.

The test is not "is this theoretically the right model?" It is "does the complexity of this model serve the people using it?" A properly normalized star schema that nobody on the team can interpret adds as much risk as a wide flat table that grows unmanageable. Start simple; add structure when the complexity is justified by actual query patterns, not anticipated ones.

<div class="takeaways">
<h2>Takeaways</h2>
<ul>
<li><strong>Use dbt snapshots for SCD Type 2, not incremental models</strong> — incremental models overwrite history; snapshots preserve it with validity windows and are the correct tool for tracking dimension changes over time.</li>
<li><strong>The point-in-time join pattern is the fundamental SCD query</strong> — joining a fact to a snapshot on both the entity key and where the fact timestamp falls within the validity window gives you dimension attributes as they were when the fact occurred.</li>
<li><strong>Degenerate dimensions stay on the fact table until they acquire their own attributes</strong> — promote order_id to a dim_orders table only when orders have header-level attributes (shipping address, discount codes, channel) that don't belong on line items.</li>
<li><strong>Role-playing dimensions need no special dbt handling</strong> — store multiple date keys on the fact table and let the BI layer alias the joins; document each key in schema.yml so the roles are unambiguous.</li>
<li><strong>Bridge tables introduce fanout — aggregate or filter before joining</strong> — joining a fact through a bridge without controlling the grain produces duplicate rows with no warning.</li>
<li><strong>A wide mart is often the right answer for simple use cases</strong> — dimensional modeling is the correct default for multi-consumer analytical products, not a requirement for every model you build.</li>
</ul>
</div>

---

What dimensional pattern have you found hardest to implement cleanly in dbt?