---
title: Your dbt layers are a suggestion until CI enforces them
date: 2026-11-19
published_at: '2026-11-19T08:11:33Z'
slug: dbt-layers-enforced-in-ci
description: Three layering rules for dbt, the dbt_project_evaluator checks behind
  each, and a CI step that blocks only the violations a PR introduces.
tags:
- dbt
- data-quality
read_time: 9
status: published
---

Run `grep -rl "source(" models/marts models/intermediate` on your dbt project. Every file it prints is a model that skipped staging, so a rename, a cast or a currency fix now lives in two places, and one copy will drift.

Nobody decided that. Someone needed a column staging didn't expose yet, the deadline was Friday, and the reviewer was busy checking the logic. A layering convention that lives in a README lasts until the first busy week. After that it's a suggestion.

<div class="post-brief">
<ul>
<li>A README can't fail a pull request, so layering quietly drifts.</li>
<li>Reviewers read the SQL and miss the lineage it changes.</li>
<li>Since dbt 2.0, the shape of your DAG can block a merge.</li>
</ul>
</div>

<div class="callout callout-info">
<span class="callout-label">the example</span>
<p>Bangka Lines is fictional: an inter-island ferry operator in the Visayas, with fares in pesos. I built it as a small dbt-duckdb project and ran every command below on dbt 2.0.12 with dbt_project_evaluator 2.0.2.</p>
</div>

---

## Layers are a contract about where decisions live

Think of a restaurant kitchen. The prep station washes and portions the vegetables once, and line cooks take from prep, never from the delivery crate. When a line cook grabs carrots straight from the crate, the dish still goes out. But now nobody can say which carrots were washed.

In dbt the prep station is staging: one model per source table, where columns get renamed and cast. Intermediate models are where joins and business logic live. Marts are what dashboards and people query. Each layer is a promise about where one kind of decision gets made, and the folders only label it.

Three rules keep that promise:

1. **Only staging reads a source.**
2. **Staging reads nothing but its source.** No staging model selects from another model.
3. **A model's name tells the truth about its layer.**

<figure>
<picture>
<source media="(max-width: 600px)" srcset="../assets/posts/dbt-layers-enforced-in-ci/layer-rules-mobile.svg">
<img src="../assets/posts/dbt-layers-enforced-in-ci/layer-rules.svg" alt="Four columns, sources, staging, intermediate and marts, joined by green arrows that flow left to right one layer at a time. Below them, three pairs of red-bordered boxes linked by dashed red arrows show the forbidden edges: a source straight into a mart, one staging model into another, and a mart back into staging.">
</picture>
<figcaption>Allowed edges move one step to the right. Every red edge is a decision made in the wrong place.</figcaption>
</figure>

The Bangka Lines model `fct_sailing_load` breaks rule 1. It counts seats sold per sailing, but it reads raw bookings directly instead of `stg_booking__bookings`:

```sql
SELECT
    s.sailing_id
    , s.route
    , s.seats
    , COUNT(b.booking_id) AS seats_sold
FROM {{ ref('int_sailings_with_vessel') }} AS s
LEFT JOIN {{ source('booking', 'bookings') }} AS b
    ON s.sailing_id = b.sailing_id
GROUP BY s.sailing_id, s.route, s.seats
```

The query is correct today. The day staging starts filtering out test bookings, this mart won't get the memo.

---

## The checks behind each rule

A check works like a building inspector who reads the blueprint before anyone pours concrete. dbt 2.0 added [checks](https://docs.getdbt.com/docs/build/checks): SQL queries over your project's metadata that run locally in DuckDB, with no warehouse connection. A check passes when it returns zero rows. If a check with `severity: error` fails, `dbt build` stops before compiling a single model. [dbt_project_evaluator](https://dbt-labs.github.io/dbt-project-evaluator/latest/rules/modeling/) 2.x ships its rules as checks, and seven of them map onto the three rules:

<div class="ts-block">
<div class="ts-row">
  <span class="ts-label">rule 1</span>
  <span class="ts-desc"><strong>Only staging reads a source.</strong> <code>fct_marts_or_intermediate_dependent_on_source</code> flags a mart or intermediate model selecting from a source. <code>fct_direct_join_to_source</code> flags any model mixing a source with a ref.</span>
</div>
<div class="ts-row">
  <span class="ts-label">rule 2</span>
  <span class="ts-desc"><strong>Staging reads nothing but its source.</strong> <code>fct_staging_dependent_on_staging</code> and <code>fct_staging_dependent_on_marts_or_intermediate</code> flag staging selecting from another model. <code>fct_multiple_sources_joined</code> flags any model joining two sources.</span>
</div>
<div class="ts-row">
  <span class="ts-label">rule 3</span>
  <span class="ts-desc"><strong>Names tell the truth.</strong> <code>fct_model_naming_conventions</code> flags a prefix that doesn't match the layer. <code>fct_model_directories</code> flags a file in the wrong folder.</span>
</div>
</div>

Rule 3 looks like housekeeping, but the other six depend on it. The package [decides a model's layer](https://dbt-labs.github.io/dbt-project-evaluator/latest/customization/overriding-variables/) from its prefix first (`stg_`, `int_`, `fct_`/`dim_` by default) and only falls back to the folder when no prefix matches. Bangka Lines has a `route_revenue` model in `models/marts` with no prefix, so the folder makes it a mart. Rename it `stg_route_revenue` and the evaluator judges it as staging. Only `fct_model_directories` would notice a staging model sitting in the marts folder, and moving the file silences that too. Keep that in mind for the last section.

This is the row `dbt check` printed for it, trimmed to the useful columns:

```text
check 'fct_model_naming_conventions' found with 1 violation(s)
name           model_type  appropriate_prefixes  original_file_path
route_revenue  marts       fct_, dim_            models/marts/route_revenue.sql
```

On the deliberately broken project, five of the seven layer checks failed:

<img src="../assets/posts/dbt-layers-enforced-in-ci/check-failed-terminal.png" alt="Dark terminal window running dbt check on the bangka project. Five layer checks show Failed in red, a violation table lists fct_sailing_load reading the source booking.bookings next to int_sailings_with_vessel, and the summary line reads 10 warnings and 5 errors.">

---

## Make the rules fail the pull request

Every check in the package warns by default. I want the seven layer checks to warn on my laptop and block in CI, so their severity reads an environment variable. The `&layer` anchor writes it once and `*layer` reuses it:

```yaml
# packages.yml
packages:
  - package: dbt-labs/dbt_project_evaluator
    version: [">=2.0.0", "<3.0.0"]
```

```yaml
# dbt_project.yml
checks:
  dbt_project_evaluator:
    modeling:
      fct_marts_or_intermediate_dependent_on_source:
        +severity: &layer "{{ env_var('LAYER_RULES_SEVERITY', 'warn') }}"
      fct_direct_join_to_source: {+severity: *layer}
      fct_multiple_sources_joined: {+severity: *layer}
      fct_staging_dependent_on_staging: {+severity: *layer}
      fct_staging_dependent_on_marts_or_intermediate: {+severity: *layer}
    structure:
      fct_model_naming_conventions: {+severity: *layer}
      fct_model_directories: {+severity: *layer}
```

Your project already breaks some of these rules, and you can't fix them all before Monday. You don't have to. Think of a spell-checker that only underlines what you typed today. Since version 2 of the package, [`state:modified` scopes the checks](https://dbt-labs.github.io/dbt-project-evaluator/latest/ci-check/) the same way: dbt compares your branch with the parsed project from main and reports only the resources that changed. The CI job, abridged from the package docs, parses main to get something to compare against:

```yaml
# .github/workflows/layer-rules.yml (steps only)
      - run: pip install "dbt>=2.0.0,<3.0.0"
      - name: Parse main to compare against
        run: |
          git worktree add ../base "origin/${{ github.base_ref }}"
          cd ../base && dbt deps && dbt parse
      - run: dbt deps
      - name: Layer rules on changed models
        env:
          LAYER_RULES_SEVERITY: error
        run: dbt check --select state:modified --state ../base/target
```

Both `dbt parse` and `dbt check` need a valid profile, but the checks themselves never query your warehouse.

To test it, I left the legacy `route_revenue` on main and opened a branch that adds `fct_refunds`, a new mart reading raw bookings. The check failed with exit code 1 and named only the new model. The old violation didn't block anyone.

<img src="../assets/posts/dbt-layers-enforced-in-ci/pr-state-modified.png" alt="Two panels side by side. On the left, a full-project dbt check lists violations for the legacy route_revenue and the new fct_refunds. On the right, a pull request check scoped with state:modified fails on a single row: fct_refunds reading the source booking.bookings.">

Debt you mean to keep belongs in the [exceptions variable](https://dbt-labs.github.io/dbt-project-evaluator/latest/customization/exceptions/), one named model at a time, so a full-project run can go green too:

```yaml
vars:
  dbt_project_evaluator_exceptions:
    fct_marts_or_intermediate_dependent_on_source:
      - route_revenue   # owner: revenue analytics, rebuild planned
```

<div class="callout callout-warn">
<span class="callout-label">still on dbt 1.x?</span>
<p>dbt_project_evaluator 2.x requires dbt 2.0. On dbt 1.x, pin the package to <code>["&gt;=1.0.0", "&lt;2.0.0"]</code>. There the rules are models and tests: run <code>dbt build --select package:dbt_project_evaluator</code> and set severity under <code>data_tests: dbt_project_evaluator:</code>. Version 1 evaluates the whole project on every run, so fix existing violations or add them as exceptions before you make it blocking.</p>
</div>

---

## What the checks can't see

An inspector who only reads blueprints never sees what's inside the walls. So I tried to cheat. I renamed `fct_refunds` to `stg_booking__refunds` and moved it into `models/staging/booking/`. The SQL stayed the same: one source, a filter on fares. The pull request check passed with exit code 0.

That isn't a bug. A staging model with exactly one source parent is precisely what rule 1 asks for. The checks read the edges of your DAG, so a staging model that filters, aggregates or applies business logic passes every rule.

<div class="pull-quote">
The checks read the shape of your DAG. They will never read the intent of your SQL.
</div>

One check did notice: `fct_source_fanout`, because raw bookings now fed one more model. It's a source check, though, and in dbt 2.0.x `--select` [can't scope sources yet](https://github.com/dbt-labs/dbt/issues/16554), so with `state:modified` it reports nothing. I'd close the gap two ways. An unscoped step:

```bash
dbt check fct_source_fanout   # unscoped, non-blocking step in the same job
```

And a `CODEOWNERS` entry (GitHub's file that requests reviewers by path) for `models/staging/`, so someone who cares about staging sees every new file there. A check finds the edges. A person still has to judge the logic.

<img src="../assets/posts/dbt-layers-enforced-in-ci/rename-escape.png" alt="Two pull request results stacked. The top one, fct_refunds in models/marts, fails with exit code 1 on fct_marts_or_intermediate_dependent_on_source. The bottom one has the same SQL renamed stg_booking__refunds in models/staging and passes with exit code 0, with a note that only the unscoped fct_source_fanout check sees it.">

---

## Try this at work

<div class="callout callout-tip">
<span class="callout-label">this week</span>
<p>Add the package and run <code>dbt check</code> with default severities. Count the violations of the seven layer checks. Add every existing one to the exceptions variable with a comment naming the owner. Then switch on <code>LAYER_RULES_SEVERITY=error</code> with <code>state:modified</code> in CI. From that day, a new violation needs either a fix or an exception someone signs off in review.</p>
</div>

<div class="takeaways">
<h2>Takeaways</h2>
<ul>
<li><strong>Enforcement belongs in the build</strong> — a check with <code>severity: error</code> stops <code>dbt build</code> before any model compiles.</li>
<li><strong>Three rules cover the drift I see most</strong> — sources only into staging, staging reads only its source, names match layers.</li>
<li><strong>Naming carries the other rules</strong> — the evaluator infers a model's layer from its prefix, then its folder.</li>
<li><strong>Scope CI to the change</strong> — <code>state:modified</code> blocks new violations without forcing you to fix old debt first.</li>
<li><strong>Checks see lineage, not logic</strong> — a renamed model can pass, so add an unscoped source fanout step and a code owner.</li>
</ul>
</div>

## Sources and version notes

Checked on 18 November 2026 against dbt 2.0.12 and dbt_project_evaluator 2.0.2. The source-selection limit is tracked in an open issue and may be fixed in a later 2.0.x release.

- [Checks](https://docs.getdbt.com/docs/build/checks) — dbt Developer Hub, v2.
- [Modeling rules](https://dbt-labs.github.io/dbt-project-evaluator/latest/rules/modeling/) and [structure rules](https://dbt-labs.github.io/dbt-project-evaluator/latest/rules/structure/) — dbt_project_evaluator.
- [Running the package as a CI check](https://dbt-labs.github.io/dbt-project-evaluator/latest/ci-check/) and [configuring exceptions](https://dbt-labs.github.io/dbt-project-evaluator/latest/customization/exceptions/).
- [Migrating to version 2](https://dbt-labs.github.io/dbt-project-evaluator/latest/migrating-to-v2/) — the 1.x vs 2.x differences.
- [dbt-labs/dbt#16554](https://github.com/dbt-labs/dbt/issues/16554) — `dbt check --select` can't scope source rows.
- [How we structure our dbt projects](https://docs.getdbt.com/best-practices/how-we-structure/1-guide-overview) — dbt Labs' staging, intermediate and marts guide.

Which layer rule does your project break most often, and would you have guessed it before running the check?