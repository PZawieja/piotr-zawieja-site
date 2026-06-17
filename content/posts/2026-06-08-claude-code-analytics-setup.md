---
title: "How I set up Claude Code for analytics engineering work"
date: 2026-06-08
published_at: 2026-06-08T10:00:00Z
slug: claude-code-analytics-setup
description: "Most analytics engineers re-explain their stack every AI session. CLAUDE.md, skills, and a few conventions make Claude useful from the first prompt."
tags: [AI, dbt]
read_time: 6
status: published
---

Every session starts the same way. You open a new chat, paste a model, and spend the first five minutes re-explaining: we use Snowflake, commas go at the start of lines, staging is one-to-one with sources, marts follow a specific naming convention. The AI helps. It just doesn't know your project yet.

If you've seen *Memento*, you know the condition: Leonard can't form new memories, so he tattoos the important rules onto his own body and leaves Polaroids everywhere, because relying on someone to re-explain his situation every five minutes isn't a system — it's chaos held together by Post-its. A fresh Claude Code chat has the same problem. It's extremely capable and remembers nothing about your last conversation. CLAUDE.md and AGENTS.md are the tattoos — the rules written down permanently so the agent doesn't wake up and ask "wait, what's our staging convention again?" for the fortieth time.

Claude Code can fix this — but not out of the box. With CLAUDE.md, AGENTS.md, and a handful of skills, it stops being a generic assistant and starts behaving like a senior engineer who already read your style guide. Here's the exact setup.

---

## The architecture

```
dbt-project/
├── CLAUDE.md                    ← entry point, kept short
├── .claude/
│   ├── AGENTS.md                ← conventions, stack, skills menu
│   ├── skills/
│   │   ├── develop.md           ← /develop
│   │   ├── test.md              ← /test
│   │   ├── review.md            ← /review
│   │   └── deploy.md            ← /deploy
│   └── docs/
│       ├── sql-conventions.md
│       ├── dbt-conventions.md
│       ├── yaml-conventions.md
│       └── data-warehouse.md    ← schema reference
└── models/
    ├── staging/
    ├── intermediate/
    └── marts/
```

Three layers. CLAUDE.md is short and points to AGENTS.md. AGENTS.md is the brain — it holds the conventions that would otherwise live only in your head or in a Notion doc nobody reads. The `docs/` files are lazy-loaded: a skill reads them explicitly when needed, which keeps the context window clean on simple tasks.

<div class="decision-tree">
<p class="decision-tree-title">Decision Tree: where does this go?</p>
<div class="decision-step">
<span class="decision-q">One-time orientation note</span>
<span class="decision-a"><strong>CLAUDE.md</strong> — under 20 lines, just enough to point elsewhere.</span>
</div>
<div class="decision-step">
<span class="decision-q">Stack/convention every task needs</span>
<span class="decision-a"><strong>AGENTS.md</strong> — loaded every session, so keep it tight.</span>
</div>
<div class="decision-step">
<span class="decision-q">Reference material only some tasks need</span>
<span class="decision-a"><strong>.claude/docs/*.md</strong> — lazy-loaded by a skill, not by default.</span>
</div>
<div class="decision-step">
<span class="decision-q">A repeatable multi-step workflow</span>
<span class="decision-a">A <strong>skill</strong> (<code>.claude/skills/*.md</code>) — declarative, versioned, diffable.</span>
</div>
<div class="decision-step">
<span class="decision-q">Must never modify files, only report</span>
<span class="decision-a">A <strong>sub-agent</strong> with that constraint stated explicitly — don't rely on it being implied.</span>
</div>
</div>

---

## The actual files

**CLAUDE.md** — keep it under 20 lines. Its job is orientation, not documentation:

```markdown
# Analytics Engineering Agent

Stack: dbt Core, Snowflake, Python
Conventions and skills: see .claude/AGENTS.md

## Hard rules
- Never modify production models without running dbt compile first
- All SQL uses CTEs — no subqueries
- YAML descriptions required for all mart-layer models
```

**AGENTS.md** is where the real setup lives. The placeholders are intentional — fill them in once per project:

```markdown
# Analytics Engineering Agent — Context

## Stack
- Warehouse: [YOUR_WAREHOUSE]        (e.g. Snowflake, BigQuery)
- Transformation: dbt Core [VERSION]
- Orchestration: [YOUR_ORCHESTRATOR] (e.g. Airflow, dbt Cloud)
- Schema: [YOUR_WAREHOUSE_SCHEMA]

## Directory conventions
models/staging/      → stg_[source]__[entity].sql, 1:1 with source tables
models/intermediate/ → int_[entity]_[verb].sql
models/marts/        → fct_[entity].sql, dim_[entity].sql

## SQL conventions
See .claude/docs/sql-conventions.md

## Skills
/develop  scaffold a new model from a staging source
/test     generate dbt YAML tests for an existing model
/review   read-only SQL review — flags issues, never edits
/deploy   dbt compile + dbt run for a target model

## Sub-agents
code-reviewer  reviews SQL only, never writes or modifies files
doc-reviewer   reviews YAML descriptions only
```

**The `/develop` skill** is where this setup earns its keep. Save it as `.claude/skills/develop.md`:

```markdown
# /develop

Given a target model name and layer (intermediate or mart):

1. Read the relevant staging model(s) from models/staging/
2. Read .claude/docs/sql-conventions.md and .claude/docs/dbt-conventions.md
3. Scaffold the new model SQL following naming conventions and CTE structure
4. Create the YAML schema entry in the same directory as the model
5. Run: dbt compile --select [model_name]
6. Report compile errors. Do not run dbt run without explicit confirmation.

Output: SQL file, YAML entry, compile result, list of assumptions made.
```

Short, declarative, repeatable. No ambiguity about what gets read, what gets written, what gets run.

---

## Before and after

**Before:** `write me a dbt model for MRR`

Claude invents column names, picks an arbitrary CTE style, skips the YAML, and uses a subquery because it doesn't know you've banned them — confidently, too, which is somehow worse.

**After:** `/develop fct_mrr mart`

Claude reads `stg_subscriptions.sql`, loads your SQL conventions, and produces:

```sql
-- models/marts/fct_mrr.sql
with

subscriptions as (
    select * from {{ ref('stg_subscriptions') }}
)

, monthly_revenue as (
    select
          date_trunc('month', subscription_start_date) as mrr_month
        , sum(monthly_amount_usd)                      as mrr
    from subscriptions
    where status = 'active'
    group by 1
)

select * from monthly_revenue
```

Plus the YAML entry. Plus `dbt compile` output. In one shot.

The difference isn't model quality alone — it's that you didn't have to check whether it followed your conventions, because it read them first.

---

## What this changes

**No more context re-explanation.** Conventions live in files, not in your prompt history. Close the session, come back the next day — the agent reads AGENTS.md and knows exactly where it is.

**Skills are version-controlled.** Your `/develop` skill is a file in the repo. When conventions change, you update the file. Everyone on the team gets the update on the next pull. No more tribal knowledge drift.

**Sub-agents enforce separation of concerns.** The `code-reviewer` sub-agent is instructed never to modify files. It reads, flags, and stops. You don't accidentally end up with a reviewer that "helpfully" rewrites the SQL it was supposed to review.

**Onboarding shrinks.** A new analytics engineer joins. You hand them the repo. They run `/develop` on their first ticket. The conventions are embedded in the workflow, not locked inside someone's head.

---

## 30-minute setup

**Step 1 (5 min):** Create `.claude/` in your dbt project root. Add `AGENTS.md` using the skeleton above, filling in your stack and directory conventions.

**Step 2 (10 min):** Write your SQL and dbt conventions into `.claude/docs/`. Copy from your existing style guide if you have one. If you don't — write down what you'd tell a new hire on day one. That's your conventions doc.

**Step 3 (10 min):** Write your first skill: `/develop`. Keep it under 20 lines. Explicit beats clever — the more precise the instructions, the less the skill has to guess.

**Step 4 (5 min):** Test it on a real staging model. Run `/develop [your_staging_model] intermediate`. Check the output against your actual conventions. Fix the skill file where it missed something.

That's the full loop. The first run will catch two or three gaps. Fix the skill, not the output — you want the skill to get it right next time without your intervention.

---

## What it doesn't solve

It still needs your judgment on business logic. If your MRR definition has edge cases, or your subscription data has non-standard states, the agent doesn't know that unless you document it. Hallucination on complex multi-join SQL is real, and it sounds exactly as confident when it's wrong as when it's right — that part hasn't been fixed by any model generation yet. Review the output before pushing to main — the skill reduces the surface area of what can go wrong, it doesn't eliminate it.

---

<div class="takeaways">
<h2>Takeaways</h2>
<ul>
<li><strong>Put your conventions in files, not prompts</strong> — AGENTS.md is read every session; your chat history is not</li>
<li><strong>Skills are just markdown</strong> — version-controlled, diff-able, reviewable by the whole team</li>
<li><strong>Separate write and review agents</strong> — the code-reviewer sub-agent should never modify files; enforce it in the skill definition</li>
<li><strong>Lazy-load reference docs</strong> — keep context lean by having skills explicitly load only the docs they need</li>
<li><strong>Test your skill on a real model first</strong> — the first run reveals the gaps; fix the skill file, not the one-off output</li>
</ul>
</div>

What's in your AGENTS.md right now — and what convention took you the longest to get right?
