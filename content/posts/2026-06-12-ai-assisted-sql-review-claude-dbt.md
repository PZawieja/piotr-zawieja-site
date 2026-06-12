---
title: "AI-assisted SQL review: using Claude to catch data quality issues before they ship"
date: 2026-06-12
published_at: 2026-06-12T10:00:00Z
slug: ai-assisted-sql-review-claude-dbt
description: "Not 'AI is transforming data teams' — a concrete workflow: the prompt, what it catches reliably, and where it fails. For analytics engineers who review dbt PRs."
tags: [ai, analytics-engineering, dbt, claude-code]
read_time: 8
status: published
---

SQL review in a dbt project degrades predictably. When the team is small and the project is new, reviews are careful — every CTE gets read, every join gets a question. As the project grows and PRs stack up, reviews get shallower. The standard gets set by whoever is busiest. "Looks good" becomes the default.

The bugs that slip through are not exotic. They are the same patterns, over and over:

- An incremental model with no `WHERE` clause guarding the `is_incremental()` block, so it full-scans the source on every run
- A join on a column that is not unique, inflating row counts silently
- An aggregation performed before a join, creating fanout that no one notices until a dashboard number is 3× what finance expects
- A `DISTINCT` used as a band-aid over a deduplication problem that was never fixed upstream

These patterns are predictable. Predictable means automatable.

---

## What this is not

Not a replacement for human code review. The human reviewer still owns the things that require judgment: is this the right model to build, does this metric definition match what finance agreed, is the grain correct, should this live in staging or intermediate or mart.

What Claude handles is the structural layer — the class of errors a human reviewer *would* catch if they were fresh and focused, but regularly misses when they're on their third PR of the afternoon.

The workflow:

```
PR opened → automated Claude check → human review → merge
```

Claude catches the structural problems. The human focuses on business logic.

---

## The prompt

The mistake most people make is asking Claude to "review my SQL". That produces a mix of style suggestions, observations, and genuine findings, all weighted equally. It is not useful.

The approach that works: ask Claude to check for specific failure modes only, and return nothing for patterns it does not find.

```
You are reviewing a dbt SQL model for data correctness issues only.

Check for these patterns:

1. Incremental model with no WHERE clause on the is_incremental() block —
   the model will process the full source table on every incremental run.

2. Join on a column that may not be unique — flag if no unique test is visible
   in the SQL or schema context provided. Inflated row counts will be silent.

3. Aggregation before join — a CTE that aggregates, then gets joined to a
   non-aggregated table. This is usually a fanout waiting to happen.

4. DISTINCT used as a workaround — flag DISTINCT in a position that suggests
   it is masking duplicate rows from an upstream join rather than being intentional.

5. Unused CTEs — defined but never referenced downstream.

6. Hardcoded date literals — values like '2024-01-01' that should be
   dbt variables or relative date expressions.

For each issue found: quote the relevant lines, name the pattern, describe
the consequence in one sentence. If nothing is found, say "No issues found."
Do not comment on style, formatting, or naming conventions.

Model: {{ model_name }}

SQL:
{{ sql }}
```

The constraint at the end — no style, no naming — is as important as the checklist. Without it, half the output is noise.

---

## What it catches

### Missing `is_incremental()` guard

```sql
-- models/intermediate/int_subscription_events.sql
{{ config(
    materialized='incremental',
    unique_key='event_id'
) }}

SELECT
    event_id,
    subscription_id,
    event_type,
    event_at
FROM {{ source('billing', 'subscription_events') }}
```

Claude flags this immediately: no `WHERE` clause using `is_incremental()`. Every run processes the full source table. On a small table this is invisible. On a 50-million-row events table it eventually causes a timeout or a warehouse cost spike that requires a blameless postmortem to trace.

The correct version:

```sql
SELECT
    event_id,
    subscription_id,
    event_type,
    event_at
FROM {{ source('billing', 'subscription_events') }}
{% if is_incremental() %}
WHERE event_at >= (SELECT MAX(event_at) FROM {{ this }})
{% endif %}
```

### Aggregation before join (fanout)

```sql
WITH daily_mrr AS (
    SELECT
        account_id,
        SUM(mrr_amount) AS mrr
    FROM {{ ref('int_mrr_movements') }}
    GROUP BY account_id
),

account_details AS (
    SELECT
        account_id,
        account_name,
        csm_id,
        renewal_date
    FROM {{ ref('stg_accounts') }}
)

SELECT
    d.account_id,
    a.account_name,
    a.csm_id,
    d.mrr
FROM daily_mrr d
LEFT JOIN account_details a ON d.account_id = a.account_id
```

If `stg_accounts` has multiple rows per `account_id` — historical records, duplicate imports, a staging model that was not deduplicated — the join multiplies rows silently. The `mrr` column looks reasonable per row. The total in any dashboard that sums it will be wrong.

Claude flags: aggregation in `daily_mrr`, join to `account_details` on `account_id`, no evidence `account_id` is unique in `stg_accounts`. The human reviewer then checks whether a unique test exists on `stg_accounts.account_id`. If it does, dismiss the finding. If it does not, the PR should not merge until one is added.

### Hardcoded date literal

```sql
SELECT *
FROM {{ ref('fct_revenue') }}
WHERE revenue_date >= '2025-01-01'
```

Every quarter, someone writes a model with a hardcoded cutoff date and then forgets about it. Six months later, a new team member runs a backfill that includes pre-2025 data and wonders why it never shows up downstream.

Claude flags the literal. The fix is a dbt variable:

```sql
WHERE revenue_date >= '{{ var("revenue_start_date", "2020-01-01") }}'
```

---

## Where it fails

**Business logic.** Claude does not know what "active customer" means in your domain, what the correct lookback window for your churn calculation is, or whether a particular join condition reflects a legitimate many-to-many relationship. It cannot evaluate whether a model is *correct*, only whether it contains known structural problems.

**Schema knowledge.** When it flags a potential non-unique join, it is working from the SQL it can see. If a unique test exists in `schema.yml` for the joined column, Claude cannot see it unless you include that context in the prompt. False positives on join uniqueness are the most common noise in the output.

**Subtle numeric errors.** Off-by-one period boundaries, wrong window function frames, incorrect `ROWS BETWEEN` clauses — these are logic errors that require understanding the intended calculation. Claude will not catch them.

**Intentional DISTINCT.** If a model uses `DISTINCT` deliberately — for example, deduplicating session events by design — Claude may flag it. A one-line comment in the SQL explaining the intent fixes the false positive and communicates the intent to the next human reviewer too.

In practice: roughly one false positive per five real findings. Still worth it.

---

## Three ways to integrate it

### 1. Manual, during PR review

The highest-friction option, but the right place to start. Paste the model SQL into claude.ai with the prompt above. Takes about thirty seconds per model. Worth doing manually for any model touching revenue or subscription data before committing to automation.

### 2. GitHub Actions on PR

A workflow that triggers on pull requests touching `models/**/*.sql`, collects changed files via `git diff`, and posts Claude's findings as a PR comment:

```yaml
name: SQL quality check
on:
  pull_request:
    paths: ['models/**/*.sql']

jobs:
  sql-review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: Review changed SQL models
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: python scripts/sql_review.py
```

The `sql_review.py` script collects changed `.sql` files from `git diff`, formats each with the prompt template, calls the Anthropic API, and posts findings as a PR comment via the GitHub API. Use `claude-haiku-4-5` for this — fast, inexpensive, and sufficient for pattern-matching against a fixed checklist. Cost per PR is negligible.

### 3. Claude Code skill

If you use Claude Code for analytics work, the lightest integration is a `/sql-review` skill. Create `.claude/skills/sql-review.md`:

```markdown
Read the SQL file at $ARGUMENTS (or ask which file if none given).

Check it for these data correctness issues only — skip style and naming:
- Incremental model with no is_incremental() WHERE guard
- Join on a potentially non-unique column
- Aggregation before join (fanout risk)
- DISTINCT masking an upstream deduplication problem
- Unused CTEs
- Hardcoded date literals

For each issue: quote the lines, name the pattern, one sentence on the consequence.
If nothing found, say so.
```

Then from the terminal:

```
/sql-review models/intermediate/int_mrr_movements.sql
```

The skill runs with access to your full project structure, which reduces false positives on the schema knowledge problem — Claude can read neighbouring `schema.yml` files to verify unique tests.

---

## The actual point

The patterns that slip through code review are predictable because they are boring. Nobody misses a clever architectural error — those get caught because they are interesting. What gets through is the incremental model copy-pasted from another model without updating the `WHERE` clause, the join that worked fine on dev data and quietly multiplied rows in production.

Automating the boring checklist does not make the human reviewer redundant. It makes them more focused. If the structural layer is already checked, the reviewer's attention goes to the question that actually requires their domain knowledge: is this model building the right thing.

That is the division of labour worth building.
