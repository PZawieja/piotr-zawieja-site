---
title: Reviewers can read your SQL. Show them the numbers.
date: 2026-11-25
published_at: '2026-11-25T09:07:04Z'
slug: data-pull-requests-show-the-numbers
description: 'How to write a data pull request a reviewer can approve in minutes,
  and how review should run: numbers first, grain second, style last.'
tags:
- dbt
- data-quality
read_time: 6
feature_image: ../assets/posts/data-pull-requests-show-the-numbers/cover.jpg
feature_image_alt: "Isometric illustration of two floating platforms joined by a dotted line. On the left, a person at a desk beside a tall stack of printed code holds out a single sheet. On the right, a second person looks at that sheet through a large magnifying glass that shows a small table with one gold cell and a downward arrow, next to a rubber stamp with a gold checkmark."
feature_image_caption: "Skip the pile of code. Hand the reviewer the numbers."
status: published
---

Most pull requests on data teams get reviewed by someone reading SQL. On its own, the SQL says the least about whether the numbers are right.

A reviewer can confirm that a join compiles and a column has a good name. Unless you show them, they can't see that capacity factor at one site just dropped by 13%.

<div class="post-brief">
<ul>
<li>A SQL diff hides what a change does to the numbers.</li>
<li>Review time spent on style is time not spent on joins.</li>
<li>Both sides of the review need one shared order.</li>
</ul>
</div>

<div class="callout callout-info">
<span class="callout-label">the example</span>
<p>Telhado is the fictional rooftop-solar co-op from the git series, and this is the capacity-factor change from <a href="git-metric-change-command-by-command.html">Part 2</a>. I ran the comparison query below in DuckDB on synthetic data; the numbers in the description come from that run.</p>
</div>

---

## The description is a handover note

When a nurse ends a shift, the next one doesn't re-examine every patient. The handover says what changed, what was done, and what to watch. A pull request description is the same thing, from the person who knows the change to the person who has to vouch for it.

GitHub fills every new pull request from a template if the repository has one at `.github/pull_request_template.md`. This one has five headings:

```markdown
## Why
The request in one sentence, with a link.

## What changes in the data
Models and columns touched, and how the numbers move.

## How I checked
Commands you ran and what you compared.

## Downstream and rollout
Models, dashboards or exports affected. Backfill needed?

## Not in this PR
What a reviewer might expect but won't find.
```

The second heading is the one a reviewer can't get anywhere else. The others take a minute each, and "Not in this PR" saves a round of "did you forget X?" comments.

<img src="../assets/posts/data-pull-requests-show-the-numbers/pr-description.png" alt="A dark pull request page for Telhado PR 42, Capacity factor uses installed kW and adds inverter_model. The description has the five headings filled in: a one-line why, a before and after table of capacity factor for sites PRT-027, PRT-001 and PRT-014, the dbt build command and a row count check of 42 against 42, two downstream dashboards, and a note that no backfill is needed.">

---

## Show how the numbers moved

You already have both versions of the model: production, and the copy dbt built in your development schema. One query compares them:

```sql
SELECT
    prod.site_id
    , COUNT(*) AS days_compared
    , ROUND(AVG(prod.capacity_factor), 3) AS cf_prod
    , ROUND(AVG(dev.capacity_factor), 3) AS cf_dev
    , ROUND(AVG(dev.capacity_factor) - AVG(prod.capacity_factor), 3) AS cf_change
FROM analytics.fct_daily_generation AS prod
INNER JOIN dbt_you.fct_daily_generation AS dev
    ON prod.site_id = dev.site_id
    AND prod.generation_date = dev.generation_date
WHERE prod.generation_date >= DATE '2026-11-01'
GROUP BY prod.site_id
ORDER BY ABS(cf_change) DESC
```

```text
site_id   days_compared  cf_prod  cf_dev  cf_change
PRT-027   14             0.189    0.164   -0.025
PRT-001   14             0.181    0.203    0.022
PRT-014   14             0.184    0.184    0.0
```

That table goes straight into the description, with one sentence of explanation: PRT-027 drops because its installed capacity is above its peak output, and PRT-014 doesn't move because the two are equal. Now the reviewer checks a claim instead of reverse-engineering one.

Add a row count for both tables. In my run, both were 42. When a count moves and the change wasn't supposed to add or remove rows, a join changed the grain, and that's the bug a reviewer reading SQL most often misses.

<div class="pull-quote">
A reviewer should check your claim about the numbers, not reconstruct it from the diff.
</div>

Keep the change small enough for that to work. Google's code review guide calls about 100 lines reasonable and 1,000 usually too large, and says small changes get reviewed both faster and more thoroughly. On a data team, I'd put it as one request per pull request.

---

## How review should work

A good review runs in a fixed order, most expensive bugs first. Style comes last because a linter can catch most of it before a person looks.

<figure>
<picture>
<source media="(max-width: 600px)" srcset="../assets/posts/data-pull-requests-show-the-numbers/review-flow-mobile.svg">
<img src="../assets/posts/data-pull-requests-show-the-numbers/review-flow.svg" alt="Three lanes: author, CI and reviewer. The author opens a draft pull request, CI runs dbt build and the SQL linter, and the author marks it ready for review. The reviewer responds within one business day, checking numbers, grain, tests, downstream and then nits. Request changes loops back to the author, who pushes new commits. Approve leads to a squash merge.">
</picture>
<figcaption>Machines check style and builds first, so the reviewer's time goes to the numbers.</figcaption>
</figure>

<div class="ts-block">
<div class="ts-row">
  <span class="ts-label">1 · request</span>
  <span class="ts-desc">Does the description match what was asked? Wrong problem, solved well, is still wrong.</span>
</div>
<div class="ts-row">
  <span class="ts-label">2 · numbers</span>
  <span class="ts-desc">Do they move the way the description says? Spot-check one site or one day yourself.</span>
</div>
<div class="ts-row">
  <span class="ts-label">3 · grain</span>
  <span class="ts-desc">Can any join duplicate rows? Row counts before and after answer this fast.</span>
</div>
<div class="ts-row">
  <span class="ts-label">4 · tests</span>
  <span class="ts-desc">New columns documented, keys tested with <code>not_null</code> and <code>unique</code>.</span>
</div>
<div class="ts-row">
  <span class="ts-label">5 · downstream</span>
  <span class="ts-desc">Who reads this model, and do they know the number changes?</span>
</div>
<div class="ts-row">
  <span class="ts-label">6 · nits</span>
  <span class="ts-desc">Anything left, prefixed <code>nit:</code> so the author knows it's optional.</span>
</div>
</div>

Three habits make that order stick:

- **Answer within one business day.** That's the maximum in Google's guide, and it's what stops reviews from becoming the team's bottleneck.
- **Approve when it's better, not when it's perfect.** Google's senior principle is to approve once a change definitely improves the codebase. Use GitHub's Request changes for what would break numbers, and a comment for everything else.
- **Open drafts early.** A draft pull request can't be merged and doesn't ping code owners, so CI can run while you finish. Mark it ready when the description is filled in.

The author has a job too: reply to every comment, push fixes as new commits so the reviewer sees only what changed, and re-request review.

<img src="../assets/posts/data-pull-requests-show-the-numbers/review-order.png" alt="A checklist card titled review a data pull request in this order, listing six numbered steps: request, numbers, grain, tests, downstream and nits, each with a one-line question. A strip at the bottom reads respond within one business day, approve when it is better, not perfect.">

---

## Try this at work

<div class="callout callout-tip">
<span class="callout-label">today</span>
<p>Commit the template above as <code>.github/pull_request_template.md</code>. On the next pull request you review, read "What changes in the data" before you open the diff. If that section is empty, ask for it before you comment on anything else.</p>
</div>

<div class="takeaways">
<h2>Takeaways</h2>
<ul>
<li><strong>The SQL diff is the least informative part</strong> — reviewers need to see how the numbers move.</li>
<li><strong>Compare prod and dev in one query</strong> — paste the before and after into the description.</li>
<li><strong>Row counts catch grain bugs</strong> — a count that moves unexpectedly means a join changed.</li>
<li><strong>Review in a fixed order</strong> — request, numbers, grain, tests, downstream, then nits.</li>
<li><strong>Fast and good enough beats slow and perfect</strong> — one business day to respond, approve when it's better.</li>
</ul>
</div>

## Sources and version notes

Checked on 20 November 2026. I ran the comparison query on DuckDB with synthetic data; the schema names are illustrative.

- [Creating a pull request template](https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/creating-a-pull-request-template-for-your-repository) — GitHub Docs.
- [About pull requests](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/about-pull-requests) and [about pull request reviews](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/reviewing-changes-in-pull-requests/about-pull-request-reviews) — drafts and review decisions.
- Google Engineering Practices: [speed of code reviews](https://google.github.io/eng-practices/review/reviewer/speed.html), [the standard of code review](https://google.github.io/eng-practices/review/reviewer/standard.html), [small CLs](https://google.github.io/eng-practices/review/developer/small-cls.html) and [writing good CL descriptions](https://google.github.io/eng-practices/review/developer/cl-descriptions.html).

What's the last bug a reviewer caught for you, and was it in the SQL or in the numbers?