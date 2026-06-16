---
date: 2026-06-14
description: An honest assessment of which dbt packages actually earn their dependency
  weight — and which ones add complexity without proportional value.
published_at: '2026-06-14T12:19:55Z'
read_time: 7
slug: dbt-packages-worth-using-2026
status: published
tags: [dbt]
title: dbt packages worth using in 2026
---

The dbt Hub has a lot of packages. Most projects use two or three consistently and ignore the rest. The question worth answering is not "which packages exist" but "which ones earn their dependency weight" — meaning they reduce complexity, eliminate boilerplate, or catch errors that would otherwise reach production.

Here is an honest assessment of the packages that do, and the ones that don't.

---

## dbt_utils — the baseline

Almost every dbt project should have dbt_utils installed. It solves problems that are unavoidable.

**`generate_surrogate_key`** is the most-used macro in the package. When a source table lacks a reliable primary key, this hashes a list of columns into a consistent surrogate:

```sql
SELECT
      {{ dbt_utils.generate_surrogate_key(['order_id', 'line_number']) }} AS order_line_id
    , order_id
    , line_number
    , product_id
    , quantity
FROM {{ source('app', 'order_lines') }}
```

**`date_spine`** generates a complete sequence of dates — essential for cohort analyses and any model that needs to produce a row for every date in a range, including dates with no activity:

```sql
WITH spine AS (
    {{ dbt_utils.date_spine(
        datepart="day",
        start_date="cast('2024-01-01' as date)",
        end_date="cast(current_date as date)"
    ) }}
)

SELECT date_day
FROM spine
```

**`get_column_values`** enables dynamic pivots — querying the distinct values in a column at compile time and generating a CASE WHEN per value:

```sql
{% set plan_types = dbt_utils.get_column_values(ref('stg_subscriptions'), 'plan_type') %}

SELECT
      customer_id
    {% for plan in plan_types %}
    , SUM(CASE WHEN plan_type = '{{ plan }}' THEN mrr ELSE 0 END)
        AS mrr_{{ plan | lower | replace(' ', '_') }}
    {% endfor %}
FROM {{ ref('stg_subscriptions') }}
GROUP BY 1
```

`union_relations` and `star` are valuable in specific situations — merging identically-shaped tables across schemas, selecting all columns except a few — but don't see daily use.

One note on `dbt_utils.accepted_range`: it is still in dbt-utils 1.x and works fine. If you also have `dbt_expectations` installed, prefer `expect_column_values_to_be_between` there instead — it supports a `row_condition` filter and strict/non-strict bounds. If you only need basic range checks and don't want the full `dbt_expectations` dependency, `dbt_utils.accepted_range` is sufficient.

---

## dbt_expectations — better testing

dbt_expectations ports the Great Expectations library into dbt test syntax. It earns its dependency weight primarily through four tests.

**`expect_column_values_to_be_between`** — the correct replacement for `accepted_range`:

```yaml
- name: monthly_amount_usd
  tests:
    - dbt_expectations.expect_column_values_to_be_between:
        min_value: 0
        max_value: 100000
        row_condition: "status = 'active'"
```

**`expect_column_pair_values_A_to_be_greater_than_B`** — catches date ordering invariants without custom tests:

```yaml
- name: cancelled_at
  tests:
    - dbt_expectations.expect_column_pair_values_A_to_be_greater_than_B:
        column_B: started_at
        or_equal: False
        row_condition: "status = 'cancelled'"
```

**`expect_table_row_count_to_be_between`** — a sanity check that catches empty models and unexpected row count explosions:

```yaml
models:
  - name: fct_orders
    tests:
      - dbt_expectations.expect_table_row_count_to_be_between:
          min_value: 1000
          max_value: 10000000
```

**`expect_column_to_exist`** — confirms that source columns you depend on haven't been renamed or removed:

```yaml
sources:
  - name: app
    tables:
      - name: orders
        columns:
          - name: order_id
            tests:
              - dbt_expectations.expect_column_to_exist
```

What dbt_expectations does not do well: the test syntax is verbose compared to plain dbt generic tests, and error messages are harder to parse. Use it for test categories that don't have clean built-in equivalents — don't replace `not_null` or `unique` with expectations versions just for consistency.

---

## audit_helper — for migrations

audit_helper is the most underused package in the ecosystem. It solves a specific problem: you've rewritten a model and need to verify the new version produces the same results before retiring the old one.

The core workflow is a comparison query:

```sql
-- analyses/compare_revenue_models.sql
{% set old_model = ref('fct_orders_legacy') %}
{% set new_model = ref('fct_orders_v2') %}

{{ audit_helper.compare_relations(
    a_relation=old_model,
    b_relation=new_model,
    primary_key='order_id'
) }}
```

This generates a query that shows which rows exist in one model but not the other, which rows match on all columns, and which rows have value differences. It's the data diff you need for any non-trivial migration.

Reach for it when refactoring staging models, consolidating two marts, or migrating from a legacy pipeline. Do not add it to CI as ongoing test infrastructure — the comparison queries are designed for one-time validation, not for running in every PR.

---

## codegen — eliminating boilerplate

codegen generates dbt YAML from database metadata. Two macros are actually useful.

**`generate_source`** — inspects a schema and generates a `sources:` YAML block with all tables and columns:

```bash
dbt run-operation codegen.generate_source \
  --args '{"schema_name": "raw_app", "generate_columns": true}'
```

**`generate_base_model`** — generates a staging model SQL file from a source table's column list:

```bash
dbt run-operation codegen.generate_base_model \
  --args '{"source_name": "app", "table_name": "orders"}'
```

Both macros output to stdout. You copy the output, paste it into a file, and edit from there. They do not write files directly — this is intentional, since the output always needs adjustment.

The honest assessment: codegen is most valuable when onboarding a new source with many tables. For a 20-table schema, generating source YAML and base models by hand would take an hour; codegen reduces it to fifteen minutes of editing. For a single new table, writing the YAML directly is faster than looking up the macro syntax.

---

## dbt_project_evaluator — meta-testing

dbt_project_evaluator tests your dbt project structure against a set of best practices. It runs as a dbt model — it queries the dbt graph metadata and flags violations.

Checks it runs:
- Models without `not_null` tests on primary keys
- Staging models that reference other staging models (violates layer conventions)
- Sources that are not referenced by any model
- Models with no descriptions
- Marts that join directly to sources, skipping the staging layer

```yaml
# packages.yml
packages:
  - package: dbt-labs/dbt_project_evaluator
    version: [">=0.8.0", "<1.0.0"]
```

After installing, run `dbt build --select package:dbt_project_evaluator` and review the output tables in your warehouse.

The practical limitation: the default rules are opinionated and not all of them apply to every project. You will need to configure exceptions — the package provides a seed file mechanism for this. The setup investment is worth it on projects with multiple contributors where convention drift is a real risk. On a solo project, it is more rules than you need.

---

## What's not worth it

**dbt-osmosis** — auto-propagates column descriptions from parent models to children. Sounds useful; in practice the propagation logic creates maintenance confusion when descriptions should diverge downstream, and the behavior on re-runs is surprising.

**dbt-profiler** — generates column-level profiling statistics as dbt models. Useful for initial source exploration; not worth keeping as an ongoing dependency. Profile a new source once with ad-hoc queries and move on.

**re_data** — observability and anomaly detection as a dbt package. Legitimate use case, but if you need dedicated data observability, purpose-built tools (Elementary, Monte Carlo, Anomalo) are better investments than a dbt package trying to do observability in a materialisation layer.

<div class="takeaways">
<h2>Takeaways</h2>
<ul>
<li><strong>dbt_utils is the only genuinely universal package</strong> — generate_surrogate_key, date_spine, and get_column_values solve problems every project eventually hits; install it from the start.</li>
<li><strong>dbt_expectations earns its weight for four specific tests</strong> — value ranges, column pair ordering, row count bounds, and column existence checks that lack clean built-in equivalents.</li>
<li><strong>audit_helper is a migration tool, not a test framework</strong> — reach for it when rewriting a model and validating parity; don't add it to CI as ongoing test infrastructure.</li>
<li><strong>codegen pays off at onboarding scale</strong> — for a new source with 15+ tables it saves meaningful time; for a single table, writing YAML by hand is faster than looking up the macro syntax.</li>
<li><strong>dbt_project_evaluator is worth it on multi-contributor projects</strong> — enforces structural conventions that drift without enforcement; configure exceptions for rules that don't fit your project rather than disabling them entirely.</li>
<li><strong>Most other packages solve problems better addressed with standalone tooling</strong> — for profiling, one-off queries; for observability, a dedicated platform rather than a materialisation-layer workaround.</li>
</ul>
</div>

---

Which packages does your team actually use in production?