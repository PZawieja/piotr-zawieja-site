---
title: "From Excel to dbt: a realistic transition guide for Polish data teams"
date: 2026-06-05
published_at: 2026-06-05T11:00:00Z
slug: excel-to-dbt-polish-data-teams
description: "A practitioner's guide to migrating analytics from spreadsheets to dbt, covering the governance and trust-building steps that most teams skip."
tags: [dbt]
read_time: 9
status: published
---


Most Polish data teams I talk to are two to three years into a dbt migration. The ones that are struggling share a common pattern: they installed dbt, learned the syntax, and skipped the one step that makes it actually work. The step is not technical.

This guide is for teams in Warsaw, Kraków, and the wider Polish market who are somewhere in that transition — or about to start it. The technical parts are real. The process parts are the ones that actually determine whether the migration sticks.

---

## The pattern

Nearly every migration I have seen follows the same arc.

**Stage 0** looks like this: Excel and Google Sheets everywhere, shared by email or stored in a folder nobody fully controls. VLOOKUP chains three sheets deep. A "definitive" MRR calculation that lives in one person's laptop. Finance runs their own version. Customer Success runs theirs. They do not agree, and everyone has learned to live with that. It's less a data architecture than a peace treaty nobody signed.

In plain English, this is the same disagreement VAR brought to football. The replay is not the problem — everyone can see the same frozen frame of the offside line. The argument is about which moment and which body part the rule actually means, and two broadcasters can draw the line slightly differently from identical footage. Finance and Customer Success aren't disagreeing because one of their spreadsheets has a typo. They're disagreeing because nobody ever agreed on what "active customer" means, so the same underlying data produces two confident, contradictory rulings.

Then someone joins who knows SQL well. Things move to BigQuery or Snowflake. dbt gets installed over a weekend. Month one through three: it works beautifully. Clean staging models, a few marts, a DAG that makes sense. The team is proud, and they should be.

Month six through twelve: the project has forty models, Finance is still using the spreadsheet from 2022, and nobody can agree on what "active customer" means. The dbt project is technically correct. It is also not trusted.

The thing they skipped was agreeing on definitions before building models. That is not a dbt problem. That is a data governance problem, and dbt cannot solve it on your behalf.

---

## What the Polish market context means

Warsaw and Kraków data teams are often smaller than their Western European equivalents. A team of one to three analytics engineers doing everything — ingestion, transformation, dashboards, stakeholder management — is common. That structure produces strong generalists, but it leaves less time for the coordination work that makes a data platform trustworthy.

dbt skill is in high demand in Poland and supply is growing fast. What is genuinely thin is supply of people who can *govern* a dbt project — not just build models, but establish a shared metric layer, write documentation that non-technical stakeholders can read, and retire the spreadsheets in a way that earns trust rather than forcing compliance.

That governance gap is where projects break down, and it is also where the opportunity is for engineers who can close it. This is not a criticism of Polish teams specifically — it is the same pattern that played out in the UK and Germany three to four years earlier. The market catches up, and the engineers who built those skills early are now well-compensated senior practitioners.

---

## A realistic five-stage transition

### Stage 1: Document your Excel formulas as SQL before touching dbt

Before you write a single `{{ ref() }}`, open every significant Excel file and translate its logic into SQL. Not into dbt — just SQL. This forces you to find all the hidden assumptions.

```sql
-- Excel formula: =IF(AND(B2="active", C2>0), "paying", IF(B2="trial", "trial", "churned"))
-- Equivalent SQL:
SELECT
    customer_id
    , CASE
        WHEN status = 'active' AND mrr > 0 THEN 'paying'
        WHEN status = 'trial'              THEN 'trial'
        ELSE                                    'churned'
      END AS customer_segment
FROM raw.customers
```

You will find edge cases in this step. Deal with them now, in a document, before they become bugs in production.

### Stage 2: Build a staging layer that mirrors your sources exactly

No business logic in staging. Rename columns to a consistent convention, cast types, and stop there. The discipline pays off later.

```sql
-- models/staging/stg_customers.sql
SELECT
    id                                         AS customer_id
    , name                                     AS customer_name
    , status                                   AS subscription_status
    , mrr_cents / 100.0                        AS mrr
    , CAST(created_at AS TIMESTAMP)            AS created_at
    , CAST(cancelled_at AS TIMESTAMP)          AS cancelled_at
FROM {{ source('crm', 'customers') }}
```

A staging layer that contains derived logic is a staging layer you will regret in six months.

### Stage 3: Build marts that match your current Excel outputs first

Not better — identical. The goal at this stage is to produce a number your Finance team can look at alongside their spreadsheet and say "these match." Think of it the way a movie remake earns the right to change the ending: not by being objectively better on day one, but by first proving it understood the original. Resist the urge to fix things you notice along the way. Log them. Fix them in Stage 4 or later, with sign-off — fixing them now is how a trust-building project quietly turns into an eight-month rebuild nobody asked for.

```yaml
# models/marts/schema.yml
version: 2

models:
  - name: fct_monthly_revenue
    description: >
      Monthly recurring revenue by customer, matching the Finance MRR report.
      Definition: sum of active subscriptions in the billing period.
      Verified against Finance spreadsheet v2.3 (2026-05-01).
    columns:
      - name: customer_id
        tests:
          - not_null
          - unique
      - name: mrr
        tests:
          - not_null
```

Write the description and the verification note. When Finance asks "where did this number come from," you want a written answer ready.

### Stage 4: Add tests that catch what Excel caught through human eyes

Excel had a human reviewing it every month. dbt needs explicit tests to replace that review.

```yaml
# models/marts/schema.yml (extended)
      - name: subscription_status
        tests:
          - accepted_values:
              values: ['active', 'trial', 'paused', 'churned']
      - name: mrr
        tests:
          - dbt_utils.accepted_range:
              min_value: 0
              max_value: 50000
              inclusive: true
```

The `accepted_range` test on MRR is particularly useful. It catches the category of error where a unit conversion goes wrong and a customer suddenly has 100x their actual revenue.

### Stage 5: Retire the Excel — but not before

Run both the dbt output and the Excel in parallel for a minimum of three consecutive billing cycles. When they agree for three cycles, you have earned the right to ask the business to switch. Not before.

```python
# scripts/validate_mrr_parity.py
import pandas as pd

def check_parity(dbt_df: pd.DataFrame, excel_df: pd.DataFrame, tolerance: float = 0.01) -> bool:
    """
    Returns True if total MRR matches within tolerance across all customers.
    tolerance: relative — 0.01 means within 1 percent.
    """
    merged = dbt_df.merge(excel_df, on="customer_id", suffixes=("_dbt", "_excel"))
    merged["delta_pct"] = abs(
        (merged["mrr_dbt"] - merged["mrr_excel"]) / merged["mrr_excel"].replace(0, float("nan"))
    )
    mismatches = merged[merged["delta_pct"] > tolerance]
    if not mismatches.empty:
        print(f"Mismatches found: {len(mismatches)} rows")
        print(mismatches[["customer_id", "mrr_dbt", "mrr_excel", "delta_pct"]].head(10))
        return False
    print("Parity check passed.")
    return True
```

Running this script before each month-end close builds a paper trail that makes the retirement conversation much easier.

---

<div class="decision-tree">
<p class="decision-tree-title">Decision Tree</p>
<div class="decision-step">
<span class="decision-q">If Finance and CS already disagree on a metric</span>
<span class="decision-a">Stop. Resolve the <strong>definition</strong> before writing a single dbt model — the migration cannot fix a disagreement the business hasn't settled.</span>
</div>
<div class="decision-step">
<span class="decision-q">If dbt's number differs from the Excel it replaces</span>
<span class="decision-a">Assume the dbt model is wrong until proven otherwise — not the spreadsheet, even if you suspect the spreadsheet has flaws.</span>
</div>
<div class="decision-step">
<span class="decision-q">If parity holds for fewer than three billing cycles</span>
<span class="decision-a">Keep running both systems in parallel — one good week is not three good months.</span>
</div>
<div class="decision-step">
<span class="decision-q">If a stakeholder asks "where did this number come from" and you don't have a written answer</span>
<span class="decision-a">The model isn't ready to ship, regardless of test coverage.</span>
</div>
<div class="decision-step">
<span class="decision-q">If you spot a number you want to "fix" while matching Excel</span>
<span class="decision-a">Log it. Fix it later, with sign-off — not in the same pass where you're trying to earn trust.</span>
</div>
</div>

---

## The one thing that makes it stick

The transition fails when dbt is treated as a technical upgrade and succeeds when it is treated as a trust-building project.

Business stakeholders do not care about DAGs, lineage graphs, or the elegance of your staging layer — reasonably so, since nobody has ever closed a deal by admiring a DAG. They care about whether the numbers they present to their manager on Friday morning are correct. That concern is legitimate. Their previous system — the spreadsheet — had a human checking it. Your new system needs to earn the same confidence through consistency and transparency, not through a one-time demo.

Write the documentation before anyone asks for it. Define "active customer" in your schema.yml before Finance asks why dbt's count differs from theirs. Set up the parity tests before the first month-end. Make the process visible.

The Polish data market is moving fast. Senior analytics engineers who can take a team through this transition — combining technical depth with the stakeholder work — are in genuinely short supply. The teams that invest in this skill set are building something durable.

---

<div class="takeaways">
<h2>Takeaways</h2>
<ul>
<li><strong>Definitions first, models second</strong> — agreeing on what "active customer" means before writing SQL is not optional; it is the work that makes everything else hold together.</li>
<li><strong>Staging layers should be boring</strong> — no business logic, just renaming and casting; complexity belongs in marts where it can be tested and documented.</li>
<li><strong>Match before you improve</strong> — producing identical output to the existing spreadsheet, even if you know it has flaws, is how you build the trust that lets you fix those flaws later.</li>
<li><strong>Run parallel for three cycles</strong> — three consecutive billing periods of parity between dbt output and Excel gives you evidence; one week of matching numbers does not.</li>
<li><strong>Governance is the gap</strong> — in the Polish market right now, the scarce skill is not dbt syntax but the ability to govern a metric layer and retire spreadsheets through stakeholder buy-in rather than mandate.</li>
</ul>
</div>

---

What was the hardest part of your own Excel-to-dbt migration — the technical side, or getting the business to trust the new numbers?
