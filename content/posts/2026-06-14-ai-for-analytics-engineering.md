---
date: 2026-06-14
description: Not a hype piece. A practical map of where AI tools earn their place
  in an analytics engineering workflow — and the categories where they consistently
  fall short.
published_at: '2026-06-14T12:31:51Z'
read_time: 8
slug: ai-for-analytics-engineering
status: published
tags: [AI]
title: 'AI for analytics engineering: where it actually helps and where it doesn''t'
---

The pitch for AI in data work has been consistent for two years: write SQL faster, generate documentation automatically, let analysts ask questions in plain English. Some of that has landed. A lot of it hasn't, or has landed in a much narrower way than advertised.

This is a practical map based on actual daily use — not what AI tools claim to do, but what they reliably do well, where they fail predictably, and how to structure your workflow around the gap between the two.

---

## Where AI consistently helps

### Boilerplate that follows a pattern

The clearest win is generating code that follows a repeatable structure you already understand. staging models, schema YAML, source definitions, generic test blocks — all of these have a learnable shape that AI replicates accurately once you give it a good example.

In practice this looks like: paste one well-written staging model into the context, describe the new source table's columns, get a draft that respects your naming conventions, column ordering, and casting patterns. You spend ten minutes editing instead of thirty minutes writing from scratch.

The same applies to schema YAML. Generating `not_null` and `unique` tests on every primary key, `accepted_values` on status columns, `relationships` tests on foreign keys — this is mechanical work that AI handles well. You still review and adjust, but the first draft is 80% right.

### SQL review for structural errors

AI is a reliable second reviewer for the category of SQL bugs that are structural rather than semantic — the errors a careful human reviewer would catch if they were fresh, but regularly misses on the third PR of the afternoon.

The patterns it catches consistently:

- Incremental models with no `is_incremental()` guard on the WHERE clause, causing full-table scans on every run
- Joins on non-unique columns that silently inflate row counts
- Aggregations performed before a join, creating fanout that produces incorrect totals
- Missing `GROUP BY` columns that some warehouses accept silently
- `DISTINCT` used as a band-aid over an unfixed deduplication problem upstream

The workflow that works: paste the SQL, ask specifically for join grain issues, fanout risks, and filter logic errors. The more targeted the prompt, the more useful the output. "Review this SQL" produces generic feedback. "Check this model for join fanout and incremental filter issues" produces actionable findings.

### Documentation generation from existing code

Given a well-written SQL model, AI produces accurate column descriptions at a speed no human will match. The descriptions won't be perfect — they can't know that `customer_segment` maps to a specific tier structure your sales team defined in 2023 — but they are correct about what the SQL does, and they are a much better starting point than an empty YAML file that never gets filled in.

The honest constraint: documentation AI generates is about code behavior, not business meaning. "Monthly recurring revenue in USD, summed from active subscriptions" is accurate. "The MRR figure used in board reporting, which excludes trial subscriptions per finance team agreement" requires a human who knows the business context. AI gives you the first kind. You provide the second.

### Explaining unfamiliar SQL patterns

When you inherit a codebase with patterns you haven't used — recursive CTEs, complex window function chains, dynamic SQL generation in Jinja — AI explains them accurately and quickly. This is one of the most underrated uses: not writing new code, but understanding existing code well enough to modify it safely.

---

## Where AI predictably fails

### Metric definitions and business logic

This is the most important failure mode to understand, because it is also the place where the hype is loudest.

AI does not know what your business means by "active customer." It does not know whether your MRR calculation should include trial subscriptions, whether a paused subscription counts as churned for cohort analysis, or which product lines are excluded from the revenue metric your CFO uses. It has no access to the Slack thread where your data team and finance agreed on that definition last quarter.

When you ask AI to write a revenue model, it will produce plausible SQL. The SQL will run without error. The numbers will look reasonable. They will also be wrong in ways that take weeks to surface, because the model made reasonable-seeming assumptions about your business that happen to be incorrect for your specific context.

The correct use of AI in metric work is narrow: once you have defined the metric precisely and written the SQL yourself, AI can review the implementation for structural errors. It cannot define the metric for you.

### Grain decisions

The hardest decisions in data modeling are grain decisions: should this fact table be at the order grain or the order-line grain? Should this model be a wide mart or a normalized dimension? Should subscription events be tracked as a slowly changing dimension or a point-in-time snapshot?

AI produces confident-sounding answers to these questions. Those answers are not grounded in knowledge of your query patterns, your BI tool's behavior, your team's SQL proficiency, or the downstream consumers who will actually use the model. Grain decisions require that context. AI does not have it.

### Debugging wrong numbers in production

"My revenue figure is 12% higher than last month with no change in the business" is exactly the kind of problem that looks like it should be solvable with AI assistance. In practice, diagnosing it requires understanding the data model, knowing what changed in upstream sources, understanding the business context, and being able to run exploratory queries against the actual data.

AI can suggest a debugging checklist — check for new rows in source tables, look for filter drift, audit the incremental lookback window. That checklist is useful. But the actual debugging work requires a human who can run queries, read the results, and connect technical findings to business events. AI can assist at the margins; it cannot replace the investigative work.

### Code that touches undocumented business rules

Every mature analytics project has undocumented business rules encoded in SQL: the `WHERE customer_type != 'internal'` filter that excludes test accounts, the `CASE WHEN` that maps legacy product codes to current product names, the date offset that aligns your fiscal calendar. These rules exist because someone made a decision that was never written down.

AI does not know these rules exist. When you ask it to generate or refactor code in an area that depends on them, it will produce technically correct SQL that silently violates the business logic. The result looks clean and runs cleanly. The numbers are wrong.

---

## The workflow that actually works

The pattern that produces the best results is treating AI as a skilled technical collaborator who is new to your business — someone who writes clean code and catches structural errors but needs explicit briefing on anything domain-specific.

**What to give AI:**
- A concrete, specific task ("generate the schema YAML for this model", "review this JOIN for fanout risk")
- Enough context to be useful (the model it's reviewing, the grain it should expect, the conventions it should follow)
- A worked example when you want it to match an existing pattern

**What to keep human:**
- Any decision that requires business context (metric definitions, grain choices, what data means)
- Debugging that requires running queries and reading results
- Final review before anything ships — AI review is a first pass, not a sign-off

**The right mental model:** AI is good at the 40% of analytics engineering work that is mechanical — generating boilerplate, checking structure, explaining code, drafting documentation. The other 60% — the business logic, the grain decisions, the debugging, the stakeholder alignment — requires the judgment that comes from knowing your data, your business, and your consumers. That part doesn't get shorter with AI; it gets more visible, because the mechanical work stops consuming your time.

---

## The tools worth using today

**Claude Code / Cursor** for SQL review and boilerplate generation in your editor. The in-editor context window matters — being able to reference multiple files in the same project produces better output than copy-pasting into a chat interface.

**codegen** (dbt package) for source YAML and base model generation — not AI, but it solves the same boilerplate problem for the specific case of onboarding new sources.

**Snowflake Cortex Analyst / BigQuery Gemini** for natural language querying against a governed semantic layer. The qualifier "governed semantic layer" is load-bearing — these tools work when the metric definitions are already encoded in a semantic model, and fail when pointed at raw tables.

**GitHub Copilot** for SQL completion in editors that support it. Most useful for writing repetitive patterns (CASE WHEN blocks, date trunc expressions) where the completion is mechanical. Less useful for anything that requires business context.

What's not worth using yet: any AI tool that claims to generate production-ready data models from a schema description alone. The structural output is fine. The business logic it encodes will be wrong in ways that are hard to audit.

<div class="takeaways">
<h2>Takeaways</h2>
<ul>
<li><strong>AI is reliable for mechanical work, not judgment work</strong> — boilerplate generation, structural SQL review, and documentation drafting are consistent wins; metric definitions, grain decisions, and production debugging are not.</li>
<li><strong>The most dangerous failure mode is plausible-looking wrong output</strong> — AI-generated SQL that runs cleanly but encodes incorrect business assumptions is harder to catch than a failing query.</li>
<li><strong>Targeted prompts produce useful output; vague prompts produce generic output</strong> — "check for join fanout and incremental filter issues" returns actionable findings; "review this SQL" returns a checklist you already know.</li>
<li><strong>AI cannot know your undocumented business rules</strong> — the filters, mappings, and date offsets that encode decisions never written down are invisible to any AI tool. Code that touches them needs human review.</li>
<li><strong>In-editor context beats copy-paste chat</strong> — tools that can reference multiple files in your project produce materially better output than isolated prompts without surrounding context.</li>
<li><strong>Natural language querying requires a governed interface first</strong> — AI querying tools work when metric definitions are encoded in a semantic model; they produce wrong answers when pointed at raw tables.</li>
</ul>
</div>

---

What's the most useful thing AI has done in your analytics workflow — and where has it burned you?