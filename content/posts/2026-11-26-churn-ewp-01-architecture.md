---
title: 'Building a Churn Early-Warning Platform, Part 1: Architecture Before SQL'
date: 2026-11-26
slug: churn-ewp-01-architecture
description: Most engineers start with SQL. The skill is knowing what to build before
  touching the keyboard — three signal categories, one dbt layer design, one controversial
  first-version choice.
tags:
- dbt
- AI
read_time: 9
feature_image: ../assets/posts/churn-ewp-01-architecture/cover.jpg
feature_image_alt: "Isometric illustration of three floating platforms joined by a dotted line. On the left, a person files folders beside a filing cabinet. In the middle, two people stand at a scale under a large risk gauge whose needle points toward red, next to a stack of cards, a glass box of gears and a weekly calendar with pinned notes. On the right, a person in a headset sits at a desk with an inbox tray, a phone and a small gold flag."
feature_image_caption: "Account data in, a risk score in the middle, a short list for the CSM at the end."
status: published
published_at: '2026-11-26T09:06:44Z'
---

The most expensive line of SQL in a churn project is the first one. It quietly makes architecture decisions that nobody wrote down.

So before I wrote any SQL for this project, I spent a session answering questions. What data do I have? Which signals predict churn 6–8 weeks out? What does a customer success manager (CSM) need in hand to act? Most engineers I've worked with skip this part. They have data, they know SQL, so they start querying, and the shape of their first model becomes the architecture by accident. Accidental decisions are the hardest ones to unpick later.

<div class="post-brief">
<ul>
<li>Skip the design and your first SQL model becomes the architecture.</li>
<li>B2B churn runs on renewal dates and accounts, which changes everything.</li>
<li>Every later part of this series hangs on these decisions.</li>
</ul>
</div>

<div class="callout callout-info">
<span class="callout-label">series</span>
<p>Part 1 of <em>Building a Churn Early-Warning Platform</em>: Part 1: Architecture before SQL (this post) · Part 2: The account × week spine · Part 3: Feature engineering · Part 4: Scoring, alerts & history · Part 5: One file, no server · Part 6: When the ML model disagrees</p>
<p>Code: <a href="https://github.com/PZawieja/churn-early-warning-platform">github.com/PZawieja/churn-early-warning-platform</a></p>
</div>

This post is that session: why B2B churn is its own problem, which signals I picked and how I weighted them, why version one uses rules instead of ML, and why DuckDB runs the whole thing on a laptop. The code starts in Part 2. This part decides whether the code is any good.

---

## Why B2B churn is different

Consumer churn and B2B churn are different animals. In B2C, a user stops a $9-a-month subscription: high volume, mostly self-serve. In B2B SaaS, a customer cancels an account that might represent $50k ARR, the decision involves multiple stakeholders, and there was almost certainly a renewal date on a calendar somewhere. These differences have direct implications for how you model churn signals.

The most important difference is the renewal date. B2C churn is a continuous probability: on any given day, a user might cancel. B2B churn has a hard deadline. An account that looks risky at 120 days to renewal is a slow burn. The same account at 14 days is a fire. The scoring system has to encode this urgency, not just risk in the abstract.

The second difference is signal cadence. Consumer products measure daily active users, daily sessions, daily conversions. B2B usage is slower and noisier. A power user logs in Monday and Friday, an occasional user logs in on the last day of the month to run their one required report. Weekly aggregation smooths this noise in a way daily doesn't. Looking at WAU trends rather than DAU means you're measuring genuine engagement shifts rather than day-of-week patterns.

The third is the unit of analysis. You monitor accounts, not individual users. A team of 20 people that has 3 active users this week is a problem, regardless of which 3 users those were. The ratio of active users to contracted seats (`active_user_ratio`) carries information that raw WAU doesn't.

---

## Three signal categories, one weighting decision

After reviewing the available data sources, I settled on three categories of signal.

<div class="tradeoff-grid">
<div class="tradeoff-row header">
  <span class="tradeoff-cell">Component</span>
  <span class="tradeoff-cell">Weight</span>
  <span class="tradeoff-cell">Signals</span>
</div>
<div class="tradeoff-row">
  <span class="tradeoff-cell">Usage</span>
  <span class="tradeoff-cell">45%</span>
  <span class="tradeoff-cell">WAU trend, active_user_ratio, feature breadth, days since last event</span>
</div>
<div class="tradeoff-row">
  <span class="tradeoff-cell">Commercial</span>
  <span class="tradeoff-cell">30%</span>
  <span class="tradeoff-cell">days_to_renewal, seat utilization, payment failure, downgrade events</span>
</div>
<div class="tradeoff-row">
  <span class="tradeoff-cell">Support</span>
  <span class="tradeoff-cell">25%</span>
  <span class="tradeoff-cell">P1/P2 ticket volume, open backlog, avg resolution days</span>
</div>
</div>

Usage gets the highest weight because it's the strongest leading indicator. An account whose WAU has dropped 50% over 4 weeks is showing you something real before it shows up anywhere else. Commercial signals come second for a different reason: they change how urgent a given risk score is. The `days_to_renewal` component of the commercial score is the reason a MEDIUM-risk account in a 90-day renewal window gets an alert while an identical account with a year to go doesn't. Support gets 25%. P1/P2 escalations are genuinely predictive, but they lag the real problem: accounts in trouble file more tickets, and the tickets are the symptom.

The weights are hypotheses at this stage, not findings. I have a prior about which signals matter and how much. Part 6 covers what happens when a logistic regression model is trained on the same feature set and disagrees — in ways that are worth examining carefully.

<div class="callout callout-info">
<span class="callout-label">context</span>
<p>The 45/30/25 split came from reasoning about signal timing and actionability, not from a training run. When you're building version one of a scoring model, your best tool is a clear head and domain knowledge. The ML upgrade is valuable precisely because you have a rule-based baseline to evaluate it against.</p>
</div>

Risk thresholds: **HIGH ≥ 70 · MEDIUM 40–69 · LOW < 40**. Alert priority breaks HIGH and MEDIUM into four tiers: CRITICAL (HIGH + ≤14 days to renewal), URGENT (HIGH + ≤30 days), HIGH (no renewal urgency), WATCH (MEDIUM account inside 90-day renewal window). The WATCH tier is the one that earns its keep. A MEDIUM-risk account with renewal in 60 days is often more actionable than a HIGH-risk account with a year on the contract.

---

## dbt layered architecture

The data sources are four tables: `accounts` (plan, MRR, renewal date, contracted seats), `product_events` (logins, feature usage, session data), `billing_events` (payment failures, downgrades, seat changes), and `support_tickets` (volume, severity P1–P4, resolution time). The dbt architecture maps directly onto how those sources flow into a usable output.

```
Raw (seeds)
  └── stg_accounts · stg_product_events · stg_billing_events · stg_support_tickets
        └── int_account_activity_weekly  (incremental, account × week spine)
            int_account_support_signals
            int_account_billing_signals
              └── int_churn_features  (one row per account, current week)
                    └── mart_churn_risk_scores  (scored output)
                          ├── snp_churn_risk_scores  (SCD2 snapshot)
                          └── mart_churn_alerts  (CSM action queue)
```

The layers earn their place for a reason that isn't obvious on day one: they contain the blast radius of a change. Source format changes (a renamed upstream column, a new event type) touch staging only. Scoring weight changes touch one intermediate model (`int_churn_features`). CSM-facing output changes touch the mart. Without this separation, every schema change ripples across every model that touches the affected column.

<div class="pull-quote">Source format changes touch staging only. Scoring changes touch one intermediate model. The layers isolate the blast radius.</div>

Staging models are strictly 1:1 with the source: rename columns to consistent conventions, cast types, add `is_active` boolean flags. No joins, no business logic, no aggregation. If a staging model does anything more than rename and cast, it's doing too much.

Intermediate models are where all the business logic lives. The account × week spine lives here. The support signal aggregations (P1/P2 volume, resolution time) live here. The billing signal calculations (seat utilization ratio, downgrade flags) live here. The joined feature set — one row per account for the current week — lives here. These models are never queried directly by downstream tools. They exist to be joined.

Marts are what the outside world sees: `mart_churn_risk_scores` (one row per account, current risk score and tier), `mart_churn_alerts` (the CSM action queue with priority, top risk driver, and renewal date), and `snp_churn_risk_scores` (the SCD2 snapshot that makes history queryable). A Slack notification script reads `mart_churn_alerts`. A dashboard reads both marts. Neither needs to know anything about how the scores were computed.

---

## Rule-based scoring first, ML second

This is the decision people argue with most, so I'll give my reasoning straight.

A rule-based scoring model has one property that an ML model can't match in version one: it's auditable in a meeting. When a CSM asks "why is this account flagged as HIGH?" you can answer: usage score of 76 (WAU down 51%, seat utilization at 15%), commercial score of 35 (renewal in 16 days). Every number is traceable to a business rule. Any product manager can challenge any weight. When the PM says "I think support signals should be 35%, not 25%", you can change one number and re-run. The model communicates its reasoning in plain English.

An ML model gives you AUC-ROC. That's a real number and it matters, but it doesn't help a CSM understand why they're being asked to call a specific account today. Trust in the system comes first from the CSM team understanding it, and that understanding is easier to build with transparent rules than with feature importances.

The upgrade path is the second reason this sequence makes sense. The rule-based model produces a clean feature table: one row per account, named columns for every signal, consistent types. When you're ready for ML, you train on that table. The interface doesn't change. `mart_churn_risk_scores` still exists. The scoring function is replaced; everything downstream stays the same. If the rule-based model had been built as ad-hoc SQL without a clean feature layer, the ML upgrade would require a rewrite, not a swap.

<div class="callout callout-tip">
<span class="callout-label">tip</span>
<p>Build the rule-based model until a CSM uses it and trusts it. Then add ML. The argument "our ML model would be more accurate" is hard to win before anyone trusts the rule-based model that precedes it.</p>
</div>

---

## DuckDB as local dev

The production target is Snowflake. The local development environment is DuckDB, using the `dbt-duckdb` adapter.

The case for this setup: DuckDB requires zero infrastructure. No account, no credentials, no running service, no cloud spend. The database is a single file (`dev.duckdb`). `dbt run` completes in 3 seconds. You can iterate on model logic, test schema changes, and debug data issues without touching a Snowflake warehouse.

The adapter handles the abstraction. A five-line `profiles.yml` entry points to the local file for the `dev` target and to Snowflake for `prod`. The dbt models themselves don't know which database they're running against — except for a handful of syntax differences that need to be managed.

| Feature | Snowflake | DuckDB |
|---------|-----------|--------|
| Row generator | `table(generator(rowcount=>12)) + seq4()` | `unnest(range(12))` |
| Date arithmetic | `dateadd('week', -1, date)` | `date - interval '1 week'` |
| Boolean OR agg | `BOOLOR_AGG(condition)` | `bool_or(condition)` |

These traps appear in context in the posts where the affected models are built. The important thing at the architecture stage is knowing they exist and planning to handle them, either with Jinja conditionals (`{% if target.type == 'snowflake' %}`) or by choosing DuckDB-compatible syntax that Snowflake also supports (which covers most cases).

The DuckDB database name is the filename without the `.duckdb` extension. A file named `dev.duckdb` creates a database named `dev`. This matters for the three-way alignment between your profiles.yml path, your `dbt_project.yml` database variable, and your `_sources.yml` database reference — mismatch between any two of these gives you a confusing "relation not found" error.

---

## What comes next

The architecture is the contract, and every later decision about the spine, the signals and the scoring lives inside it. Part 2 covers the first and most important intermediate model: `int_account_activity_weekly`, the account × week spine that makes zero-activity weeks visible and window functions reliable.

Ever built a weekly usage report where churned accounts quietly vanished from the data? Part 2 fixes exactly that.

<div class="takeaways">
<h2>Takeaways</h2>
<ul>
<li><strong>Weekly granularity beats daily for B2B.</strong> Day-of-week patterns and occasional logins create noise. Weekly aggregation surfaces real engagement trends — and real disengagement.</li>
<li><strong>Left-join from the dimension, not the fact.</strong> Starting from accounts guarantees every account gets a row, even with zero activity. Starting from events silently drops the silent accounts.</li>
<li><strong>Rule-based first: trust is the bottleneck, not accuracy.</strong> A model a PM can challenge in a meeting earns adoption faster than a black box with better AUC.</li>
<li><strong>The upgrade path is part of the design.</strong> A clean feature table interface means swapping rule-based scoring for ML is an afternoon of work, not a rewrite.</li>
<li><strong>DuckDB lets you iterate for free.</strong> The syntax traps are real but manageable. The iteration speed advantage is significant for solo projects and small teams.</li>
<li><strong>Weights are hypotheses.</strong> The 45/30/25 split is a starting point grounded in domain reasoning. Part 6 tests those hypotheses against a logistic regression model — and finds one category was systematically underweighted.</li>
</ul>
</div>