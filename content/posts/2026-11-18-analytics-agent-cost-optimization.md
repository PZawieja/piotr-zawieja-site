---
title: "Make every token earn its place: cost optimization for analytics agents"
date: 2026-11-18
published_at: 2026-11-18T09:00:00Z
slug: analytics-agent-cost-optimization
description: "Measure cost per accepted answer, then reduce wasted model work without trading away the accuracy, freshness, and evidence users depend on."
tags: [AI]
read_time: 8
status: draft
feature_image: ../assets/posts/analytics-agent-cost-optimization/cost-per-answer.png
feature_image_alt: "A cost-per-answer diagram separates model, warehouse, and retry costs, then compares total serving spend with answers that pass the quality bar."
feature_image_caption: "Optimize for the cost of an answer that meets its quality bar, not tokens in isolation."
---

At the Lantern & Ladle night market, the prep manager asks an analytics agent: “How many bowls of sesame noodles should we prep for tonight’s concert?”

The agent fetches the full menu, months of order lines, vendor notes, weather reports, and five tool descriptions. It asks a model to add quantities that SQL could calculate exactly, retries once after a timeout, then asks a second model whether its answer sounds reasonable.

The answer may be good. But which part of that spend bought the manager confidence—and which part was a very expensive way to add noodles?

<div class="callout callout-info">
<span class="callout-label">field guide · 04</span>
<p>This is the fourth article in a practical field guide to trustworthy analytics agents. <a href="https://goldlayer.dev/writing/analytics-agent-context-engineering.html">Field guide 02</a> explains context selection; <a href="https://goldlayer.dev/writing/analytics-agent-evaluation-judges.html">field guide 03</a> explains how to measure answer quality. The market, requests, and values below are illustrative—not customer or vendor pricing data.</p>
</div>

## Measure the cost of a passing answer

Counting tokens is useful, but it does not tell you whether the agent was worth running. Track the cost of one request across its actual work:

- model input and output, including retries and any judge calls;
- cache reads and writes where the provider bills them differently;
- database or warehouse queries, including scanned data or compute;
- external tools, orchestration, and failed attempts;
- engineering or evaluation overhead separately from live serving.

Keep these categories visible. A prompt-cache hit may lower input cost while an oversized warehouse query still dominates the bill. A cheaper model may reduce the model line but require more retries—or produce fewer answers that meet the bar.

The unit that matters for this example is **serving cost per accepted answer**:

> total serving cost for a representative set ÷ answers that pass the agreed quality bar

Suppose 100 market requests cost an illustrative $4.20 to serve and 84 pass the same quality checks. That is $0.05 per accepted answer. A revised setup costs $3.60 and 90 pass, or $0.04 per accepted answer. These numbers are made up to show the calculation; they are not model prices or a benchmark. In a real comparison, run both setups on the same questions and data snapshot, and report the quality dimensions alongside the cost.

<figure>
<picture>
<source media="(max-width: 600px)" srcset="../assets/posts/analytics-agent-cost-optimization/cost-per-answer-mobile.svg">
<img src="../assets/posts/analytics-agent-cost-optimization/cost-per-answer.svg" alt="A cost ledger collects model, warehouse, and retry costs, then divides serving spend by the count of answers that pass the quality bar.">
</picture>
<figcaption>A cost reduction only counts if the answers still meet the same factual, freshness, and usability requirements.</figcaption>
</figure>

Separate experiment costs—such as running a large offline judge suite—from the cost of serving a user request. They matter to the project budget, but mixing them into a per-answer number makes operational comparisons hard to interpret. Track both.

## Find the expensive work before optimizing

Attach a request ID to every model and tool call. For each task, record the agent and prompt version, model, input and output usage, cached usage where reported, tool calls, query duration or warehouse cost, retries, and final evaluation outcome. Include percentiles and distributions, not just averages: one question that explodes into a long tool loop can disappear inside a healthy-looking mean.

Group the trace by stage:

1. **Interpretation:** Did the model need several turns to resolve a predictable request?
2. **Retrieval:** Did the agent fetch a whole catalog or raw table when a short definition and a bounded query would do?
3. **Computation:** Did a model repeat arithmetic or filtering that belongs in a governed query?
4. **Explanation:** Did the agent generate a long answer or call a judge when the user needed a simple result?
5. **Recovery:** Did an avoidable timeout, ambiguous error, or unbounded retry multiply the work?

This is where [context engineering](https://goldlayer.dev/writing/analytics-agent-context-engineering.html) and cost management meet. A concise context pack can help, but shrinking a prompt blindly is not a strategy: removing the definition, freshness timestamp, or access boundary may lower tokens and raise the cost of a wrong answer.

## Reduce work in the order that protects correctness

### 1. Let deterministic systems do deterministic work

Use the metric layer and query engine to aggregate, filter, and calculate. The model can interpret the request, choose among approved capabilities, and explain the result; it should not sum hundreds of order rows in prose. Return the smallest result that preserves the evidence the answer needs: metric, time window, units, relevant groups, sample size, and freshness.

For the night market, ask a governed service for historical orders matching the event, day of week, weather assumptions, and product. Do not give the model raw transactions and hope it performs the equivalent of a tested forecast.

### 2. Bound calls, retries, and results

Set explicit limits for tool rounds, query duration, returned rows, output size, and retry policy. Retry only errors that are plausibly transient; use backoff and an overall deadline. A permission denial, invalid metric, or malformed request is not a reason to call the same tool repeatedly.

When a result exceeds the allowed size, narrow or summarize it in the query layer. Do not silently truncate rows and present the partial set as complete. If the task cannot be completed within the budget, return a clear limitation or ask a scoped follow-up.

### 3. Reuse repeated work carefully

If many requests share stable instructions or tool schemas, measure whether the provider’s prompt caching actually hits. Keep reusable content stable and place request-specific values after it where the provider’s documented cache behavior allows. Cache eligibility, minimum lengths, retention, and prices differ; a shared agent session alone does not guarantee a cache hit.

Query-result caching is a separate decision. Its key must include the dimensions that change the answer—such as user scope, metric version, filters, and time window—and its freshness policy must match the product promise. Never reuse one user's authorized result for another user simply because the questions look alike.

### 4. Route by demonstrated need

A smaller or faster model may be enough for a bounded classification or a familiar request; a harder task may need a more capable model. Choose using the evaluation set, not a label such as “simple” inferred from one model's uncalibrated confidence. Compare task success, failure types, latency, and cost for each route. Escalate when a deterministic signal indicates ambiguity or when the response fails a check—not only when a model says it is unsure.

### 5. Treat caching and compactness as measured changes

Prompt caching can lower repeated-prefix processing cost and latency under provider-specific conditions. It does not make irrelevant context useful, and cache writes may have different rates from cache hits. Verify billed usage and the cache-read telemetry for your exact model and request shape before claiming savings.

Likewise, shorter output is not automatically better. A one-line answer may omit units, date boundaries, or a stale-data warning. Keep the minimum evidence required by the reader and test for it.

## Compare systems without buying a cheaper wrong answer

Run baseline and candidate versions on the same representative questions, snapshot, user permissions, and evaluation rubric. Report cost per request, accepted-answer rate, cost per accepted answer, latency, and the critical failure categories. For non-deterministic behavior, repeat tests where variation could change the decision.

A quality floor should block a cost optimization that breaks a must-have behavior. If the candidate saves 30% but starts confusing “orders” with “bowls” or ignores a delayed point-of-sale feed, it has not improved the product. Conversely, an expensive judge call on every routine answer may be unnecessary if deterministic checks cover the risks and human review is reserved for sampled or high-impact cases.

Set budgets at more than one level: per request, per user or tenant where appropriate, and for the system over a time window. Alert on unexpected growth in tokens, query scans, retries, or judge usage. A budget limit should produce a useful, explicit response—not a silent switch to an untested model or stale cache.

<div class="callout callout-tip">
<span class="callout-label">a useful first pass</span>
<p>Pick one common task. Capture its full serving trace, calculate its current cost per passing answer, and identify the largest avoidable stage. Change one thing, run the same eval cases, and keep the change only if quality stays above its floor.</p>
</div>

<div class="takeaways">
<h2>Takeaways</h2>
<ul>
<li><strong>Optimize the outcome, not the token count.</strong> Use cost per accepted answer alongside quality and latency.</li>
<li><strong>Instrument the complete path.</strong> Include model, cache, query, tool, retry, and evaluation costs without mixing serving and experiment budgets.</li>
<li><strong>Move exact work to exact systems.</strong> Governed queries should aggregate data; the model should interpret and explain.</li>
<li><strong>Bound work explicitly.</strong> Set limits and return honest errors instead of retrying or truncating silently.</li>
<li><strong>Measure every optimization.</strong> Provider prices and cache behavior change; verify actual usage and current terms.</li>
</ul>
</div>

## Sources and version notes

Checked on 16 November 2026. Prices, model availability, cache rules, and usage reporting change; consult current provider pricing and API documentation for your deployment.

- [OpenAI API pricing](https://developers.openai.com/api/docs/pricing) and [prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching) — current rates and provider-specific cache behavior.
- [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing) and [prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) — model pricing, cache writes, and cache hits.
- [Field guide 03: evaluating analytics agents](https://goldlayer.dev/writing/analytics-agent-evaluation-judges.html) — separating quality gates from soft scoring.

The goal is not to make every answer cheap. It is to stop paying for work that does not make the answer more correct, useful, or trustworthy.
