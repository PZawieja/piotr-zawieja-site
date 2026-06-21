---
title: 'Forecasting with an LLM vs. a real time-series model: where each one is the
  right call'
date: 2026-06-21
published_at: '2026-06-21T11:13:35Z'
slug: forecasting-llm-vs-time-series-model
description: An LLM is good at explaining a forecast, not producing one. Where Prophet
  or ETS still beats asking Claude to predict next quarter's numbers.
tags:
- AI
read_time: 9
status: published
---

Someone on the team pastes eighteen months of MRR into Claude and asks it to forecast next quarter. It comes back with three numbers, a confident paragraph about "steady month-over-month growth continuing into Q3," and no error bars. It goes into the board deck. Nobody asks how it was computed, because the paragraph sounds like it knows what it's talking about.

Sometimes that's completely fine. Sometimes it's how a real number ends up in a budget commitment with no statistical basis at all. The difference is whether you understand what the model is actually doing under the hood, and most people asking an LLM to forecast don't.

---

## What an LLM is actually doing when you ask it to forecast

An LLM has no built-in time-series machinery. When you hand it a column of monthly numbers and ask for a forecast, it isn't fitting a model — it's doing next-token-style pattern completion over a textual representation of your series, informed by whatever forecasting reasoning it picked up from training data. In practice that mostly looks like: estimate the recent trend, project it forward, round to something plausible.

That works fine when your data is close to a straight line. It falls apart the moment there's structure the model has to actually estimate rather than eyeball.

Take a retail revenue series with a real December spike. Feed an LLM 24 months of that data and ask it to forecast the next December without telling it explicitly to expect seasonality, and it will almost always under-forecast the spike — it's anchoring on the last few months it saw, which are probably not December. It has no internal concept of "seasonal period," no decomposition step, no way to separate trend from noise from a recurring cycle unless you spell the cycle out in the prompt. Tell it "this business has a strong December seasonal spike, account for that" and the output gets noticeably better — which is itself the tell. The model isn't discovering the pattern from the data; it's following an instruction you gave it.

The same gap shows up with confidence intervals. Ask for one and the LLM will produce numbers that look like an interval — a low estimate, a high estimate — but they aren't derived from anything resembling residual variance or a fitted distribution. They're a plausible-sounding spread, generated the same way the point forecast was. If you backtest them against actual outcomes, they're not calibrated. A model that says "80% confidence" should be right about 80% of the time across many forecasts. An LLM's stated confidence has no such property.

---

## What a real time-series model does that an LLM structurally can't

A statistical forecasting model — exponential smoothing (ETS), ARIMA, Prophet, or anything in that family — fits parameters to your actual data by minimizing an error function. It decomposes the series into trend, seasonality, and residual, estimates each one from the numbers you give it, and produces a forecast plus a prediction interval derived from the residual variance. None of that is approximate in the same way an LLM's output is approximate — it's the literal mechanism, not a stylistic feature of the response.

```python
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing

df = pd.read_sql(
    "SELECT month, mrr FROM analytics.fct_mrr_monthly ORDER BY month",
    con,
)

model = ExponentialSmoothing(
    df["mrr"],
    trend="add",
    seasonal="add",
    seasonal_periods=12,
).fit()

forecast = model.forecast(3)
```

That `seasonal_periods=12` line is doing the thing the LLM can't do on its own: it forces the model to estimate a recurring 12-month cycle from the data itself, not from a hint in a prompt. You also get a forecast you can backtest — hold out the last six months, fit on the rest, compare forecast to actuals with MAPE or MASE, and you have a number that tells you whether this model version is actually getting better or worse over time. That comparison doesn't exist for "ask the LLM and see if the paragraph sounds confident."

---

## Where the LLM is genuinely the right tool

This isn't an argument for never using an LLM near a forecast. It's an argument for being precise about which job it's doing.

- **Narrating the output.** A fitted model gives you a forecast, an interval, and a pile of residuals. Turning that into "Q3 is forecast at $412K, down from $430K last quarter, mainly because growth has flattened since the pricing change in May" is a job an LLM does well — it's summarizing structured output, not generating numbers.
- **Anomaly triage on residuals.** Point an LLM at the gap between forecast and actuals each month and ask it to flag the outliers and correlate them against a calendar of known events — launches, outages, pricing changes, holidays. It's good at connecting "March was 18% under forecast" to "that's the month the outage took checkout down for six hours," especially if you give it access to a changelog or incident log.
- **Qualitative what-ifs.** "We're launching a new SKU in August — how should that change our assumptions?" has no clean numeric answer from a fitted model, because there's no historical data for the new SKU. An LLM reasoning over comparable product launches, market context, and stated assumptions is a reasonable way to think through the adjustment, as long as everyone treats the output as a judgment call, not a forecast.
- **Cold start, zero history.** If a time series literally doesn't exist yet — brand-new product, brand-new market — there's nothing for ETS or Prophet to fit. An LLM reasoning from comparable products or stated assumptions is arguably more useful here than forcing a statistical model that has no signal to work with. The honest framing is "this is an estimate from analogy," not "this is a forecast."

---

## Where you need the real model, full stop

- **Anything tied to a financial commitment.** Budget, headcount, inventory orders, anything that becomes a number someone is held accountable to hitting. You need a calibrated interval, not a confident-sounding paragraph, and you need to be able to explain the method if someone asks.
- **A recurring seasonal pattern with enough history to estimate it.** If you have two or more full cycles of data, fit the cycle — don't ask a language model to eyeball it.
- **Backtestable accuracy you track over time.** If you're going to compare forecast accuracy release over release, or alert when a model's error rate creeps up, you need a metric computed the same way every time. MAPE on an LLM's output isn't meaningless, but it's measuring something different every time the underlying model version changes underneath you.
- **Reproducibility.** Same inputs, same model, same forecast — every run. An LLM's output can shift across model versions and even across runs of the same prompt in ways that are hard to pin down. That's a real problem the moment the number ends up somewhere that needs to be defensible after the fact.

<div class="tradeoff-grid">
<div class="tradeoff-row header">
<div class="tradeoff-cell">Situation</div>
<div class="tradeoff-cell">Use a real model</div>
<div class="tradeoff-cell">Use an LLM</div>
<div class="tradeoff-cell">Why</div>
</div>
<div class="tradeoff-row">
<div class="tradeoff-cell">Recurring seasonality, 2+ years of history</div>
<div class="tradeoff-cell">Yes</div>
<div class="tradeoff-cell">No</div>
<div class="tradeoff-cell">LLM only follows seasonality if you state it; the model estimates it from data</div>
</div>
<div class="tradeoff-row">
<div class="tradeoff-cell">Number feeds a budget or headcount commitment</div>
<div class="tradeoff-cell">Yes</div>
<div class="tradeoff-cell">No</div>
<div class="tradeoff-cell">Needs a calibrated interval and a defensible method</div>
</div>
<div class="tradeoff-row">
<div class="tradeoff-cell">Explaining why the forecast moved</div>
<div class="tradeoff-cell">No</div>
<div class="tradeoff-cell">Yes</div>
<div class="tradeoff-cell">Narrating structured output is a language task, not a math task</div>
</div>
<div class="tradeoff-row">
<div class="tradeoff-cell">Flagging anomalies against known events</div>
<div class="tradeoff-cell">No</div>
<div class="tradeoff-cell">Yes</div>
<div class="tradeoff-cell">Correlating residuals with a changelog or incident log is reasoning, not estimation</div>
</div>
<div class="tradeoff-row">
<div class="tradeoff-cell">Brand-new product, zero history</div>
<div class="tradeoff-cell">No</div>
<div class="tradeoff-cell">Yes (as an estimate, not a forecast)</div>
<div class="tradeoff-cell">There's no signal for a statistical model to fit</div>
</div>
</div>

---

## A workflow that uses both correctly

The pattern that holds up in practice: a dbt mart with monthly actuals feeds a scheduled Python job that fits ETS or Prophet and writes the forecast plus its prediction interval back into a mart. An LLM never touches the number. It consumes the forecast, the interval, and the residuals, and its only jobs are narration and anomaly flagging — constrained explicitly so it can't quietly replace the model's output with its own guess.

```text
You are given a fitted forecast for monthly MRR: point estimate, 80%
prediction interval, and the last 6 months of forecast-vs-actual
residuals. Do not produce a different forecast number. Write a
3-sentence summary of the trend, and flag any residual larger than
1.5x the typical deviation, naming the month and asking whether a
known event (launch, outage, pricing change) explains it.
```

That constraint — "do not produce a different forecast number" — is the whole point. It keeps the LLM in the lane where it's actually good (language, correlation, summarization) and out of the lane where it's structurally weaker than a model built for the job.

<div class="takeaways">
<h2>Takeaways</h2>
<ul>
<li><strong>An LLM extrapolates a trend; it doesn't fit a model.</strong> Without an explicit instruction, it won't discover seasonality on its own — it anchors on whatever it last saw in the series.</li>
<li><strong>LLM confidence intervals aren't calibrated.</strong> They look like an interval but aren't derived from residual variance, so they don't carry the statistical guarantee a real one does.</li>
<li><strong>Use ETS, ARIMA, or Prophet when there's history to fit.</strong> Two or more seasonal cycles of data is enough signal that guessing is the wrong tool.</li>
<li><strong>Use the LLM to narrate and flag, not to forecast.</strong> Summarizing a fitted model's output and correlating residuals with known events is a language task it's genuinely good at.</li>
<li><strong>Cold-start forecasting (zero history) is the one case where an LLM's reasoning-by-analogy is arguably more honest than forcing a statistical model to fit noise.</strong> Just label it an estimate, not a forecast.</li>
<li><strong>Anything tied to a financial commitment needs a reproducible, backtestable method.</strong> That rules out asking a model whose version and output can shift under you.</li>
</ul>
</div>

Where in your stack is a forecast currently coming from a prompt instead of a fitted model — and would anyone notice if the number were wrong?