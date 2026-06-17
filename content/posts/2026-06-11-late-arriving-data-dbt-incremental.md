---
title: "Late-arriving data: the silent failure that breaks your incremental models"
date: 2026-06-11
published_at: 2026-06-11T11:00:00Z
slug: late-arriving-data-dbt-incremental
description: "Your dbt run succeeds. Tests pass. The dashboard looks fine. The data is still wrong. Late-arriving events and the dbt patterns that handle them correctly."
tags: [dbt, data-quality]
read_time: 15
status: published
---

<p>If you've read the <a href="dbt-incremental-models-complete-guide.html">incremental models guide</a>, you know the basic pattern: filter the source to new rows, merge them in, repeat. The gap in that pattern is that "new rows" is defined by when data <em>arrived</em> — not necessarily when it <em>happened</em>. Those two things are often the same. When they're not, your model quietly produces incomplete results.</p>

    <p>No error. No failed test. Just missing data, discovered later.</p>

    <hr>

    <h2>What is late-arriving data?</h2>

    <p>Late-arriving data is any record that reaches your pipeline <em>after</em> the time window it belongs to has already been processed.</p>

    <p>An event that happened on Monday but didn't reach your warehouse until Wednesday is late-arriving data. Your incremental model ran on Monday night with a filter of <code>event_time &gt; last_run</code>. Wednesday's run has a watermark of Wednesday. Monday's late event arrives and falls below the watermark. It never gets processed.</p>

    <p>The event exists in the source system. It exists in the staging table. It just never made it into your marts — and nothing told you that.</p>

    <p>Think of a transit app's live arrivals board. A bus actually passes your stop at 8:02 — that's the event. But the bus's GPS unit only reports back to the server once it clears a dead zone five minutes later — that's when the data arrives. If the app's board only shows "pings received since I last checked," and it checked at 8:04, that 8:02 bus never appears. It happened. The board just never heard about it in time. Your incremental model has the exact same blind spot, just with rows instead of buses.</p>

    <hr>

    <h2>Why it happens</h2>

    <p>Late arrivals have several root causes, and most production data pipelines encounter more than one of them.</p>

    <h3>Mobile apps and offline events</h3>

    <p>A user opens your app on a train with no signal and generates a session's worth of events — clicks, views, purchases. Their phone queues those events locally. Two hours later they connect to WiFi, and all of them flush to your backend at once. The <code>event_time</code> values are from the train. The <code>arrival_time</code> is from the airport.</p>

    <p>This is expected behavior from the SDK. It's also a guarantee that if you filter by <code>event_time &gt; last_run</code>, the offline session will be missed on any incremental run that happened before the user reconnected.</p>

    <p>Your incremental model, meanwhile, has no idea anyone was ever on a train.</p>

    <h3>Webhook retries</h3>

    <p>Payment processors, subscription billing platforms, and CRMs send webhooks for every state change. When the receiving endpoint is down or responds with a non-2xx status, they retry — sometimes for hours, sometimes across days. The webhook body contains the original <code>created_at</code> timestamp of the event. The delivery happens later.</p>

    <p>A failed payment on Monday, a webhook that didn't deliver until Tuesday night, and an incremental subscription model that ran Monday at midnight: the failed payment event is missing from Monday's data. Your churn calculation for Monday is understated by exactly those records.</p>

    <h3>Third-party batch exports</h3>

    <p>Many SaaS CRMs and billing systems don't have real-time APIs — they export data in daily or hourly batches. A deal closed on Tuesday at 4pm may not appear in your Salesforce export until Wednesday's 3am sync. Your Tuesday incremental run finished before that data existed in the source.</p>

    <p>Worse: some systems export only the <em>current state</em> of records in each batch. Historical closes, retroactive adjustments, and backdated entries are delivered in a later batch with their original effective date intact.</p>

    <h3>ETL pipeline failures and backfills</h3>

    <p>Your Fivetran or Airbyte connector fails at 2am during a network disruption. It recovers at 6am and backfills the four-hour window it missed. The records arrive at 6am with <code>event_time</code> values from the 2–6am window. If your incremental model ran at 5am and filtered on <code>ingested_at</code> rather than <code>event_time</code>, the backfill is fine — it arrives after the model ran and will be picked up next time. If your model filtered on <code>event_time</code>, the backfill lands in a window that's already been processed.</p>

    <h3>Database replication lag</h3>

    <p>Log-based CDC replication (Debezium, DMS, Fivetran change data capture) can fall behind under load. Updates and inserts that happened at 10am can arrive in your warehouse at 11am or later, attributed to their original transaction timestamps.</p>

    <hr>

    <h2>Why it is dangerous</h2>

    <p>The core risk is not that your data is wrong — it's that it looks correct while being wrong. A data quality check that passes is doing its job. A count of events per day that looks plausible is not the same as a count that is complete.</p>

    <p>The practical consequences compound over time:</p>

    <ul>
      <li>A daily subscription churn model counts 14 churned accounts. Three more arrive the next morning as late webhook retries. The snapshot for yesterday is now permanently short by three records — and whatever report referenced it is quietly incorrect.</li>
      <li>A conversion funnel missing 1.5% of mobile events consistently understates conversion rates. The optimization recommendations built on top of that funnel are based on wrong data for months before anyone notices.</li>
      <li>An MRR calculation built on incremental staging models is off by a small but consistent amount because backfilled Chargebee events keep landing outside the watermark window. The discrepancy surfaces during a quarterly reconciliation, not when it happens.</li>
      <li>Data quality alerts on row counts don't fire because the counts look reasonable — slightly low, but within tolerance. The late data doesn't make the number obviously wrong, just slightly wrong.</li>
    </ul>

    <p>The warehouse doesn't know data is missing. It reports what it has. The model succeeded. The tests passed. Everything is fine, except for the data that isn't there.</p>

    <p>Ask a warehouse if it's missing anything and it will cheerfully say no. It does not know what it does not know, and it is remarkably confident about that.</p>

    <hr>

    <h2>The timestamp problem</h2>

    <p>Before choosing a pattern, it helps to be precise about which timestamps you're dealing with. Most event-generating systems produce at least three distinct timestamps, and conflating them is the root cause of most late-data handling failures.</p>

    <div class="ts-block">
      <div class="ts-row">
        <div class="ts-label">event_time</div>
        <div class="ts-desc">When the thing happened in the real world. Set by the application or client device. Can be wrong due to clock drift, timezone errors, or offline buffering. Not reliable for pipeline ordering.</div>
      </div>
      <div class="ts-row">
        <div class="ts-label">arrived_at / created_at</div>
        <div class="ts-desc">When the source system received or recorded the event. More reliable than event_time but still subject to batch delays and CRM processing windows.</div>
      </div>
      <div class="ts-row">
        <div class="ts-label">ingested_at</div>
        <div class="ts-desc">When your pipeline (Fivetran, Airbyte, custom connector) pulled the record into your warehouse. Usually stored as _fivetran_synced, _airbyte_extracted_at, or similar. The most reliable timestamp for pipeline scheduling.</div>
      </div>
    </div>

    <p>The correct split for incremental models:</p>

    <ul>
      <li>Use <code>ingested_at</code> in your incremental filter — "process everything the pipeline received since the last run"</li>
      <li>Use <code>event_time</code> in your business logic — "count events that occurred in this calendar window"</li>
    </ul>

    <p>Filtering on <code>event_time</code> for both looks simpler. It misses any record where the pipeline received it before your watermark, regardless of when the event happened. Filtering on <code>ingested_at</code> guarantees pipeline completeness — every record the connector delivered is processed — while <code>event_time</code> attributes it to the correct business window.</p>

    <p>The tradeoff: filtering on <code>ingested_at</code> means your incremental model sees late-arriving records as "new" when the pipeline delivers them. With a merge strategy and a good <code>unique_key</code>, those records are inserted correctly rather than silently dropped.</p>

    <hr>

    <h2>Patterns for handling late-arriving data</h2>

    <h3>Pattern 1: The lookback window</h3>

    <p>The simplest and most widely applicable fix. Instead of filtering to rows newer than the last run's watermark, reprocess a fixed window of recent time.</p>

<pre><code><span class="tag">{{</span> config(
    materialized=<span class="string">'incremental'</span>,
    unique_key=<span class="string">'event_id'</span>,
    incremental_strategy=<span class="string">'merge'</span>
) <span class="tag">}}</span>

<span class="keyword">SELECT</span>
    event_id
    , user_id
    , event_type
    , event_time
    , _fivetran_synced <span class="keyword">AS</span> ingested_at
<span class="keyword">FROM</span> <span class="tag">{{</span> source(<span class="string">'app'</span>, <span class="string">'raw_events'</span>) <span class="tag">}}</span>

<span class="tag">{%</span> <span class="keyword">if</span> is_incremental() <span class="tag">%}</span>
<span class="keyword">WHERE</span> _fivetran_synced &gt;= <span class="keyword">DATEADD</span>(day, -3, (<span class="keyword">SELECT MAX</span>(ingested_at) <span class="keyword">FROM</span> <span class="tag">{{</span> this <span class="tag">}}</span>))
<span class="tag">{%</span> <span class="keyword">endif</span> <span class="tag">%}</span></code></pre>

    <p>On every run, this reprocesses the last 3 days of ingested records. The merge strategy deduplicates using <code>event_id</code> — records already in the table are updated if they changed, genuinely new late-arriving records are inserted.</p>

    <p>How far back to look: match your window to the SLA of your slowest source. Webhook retry windows are typically 24–72 hours. Batch CRM exports are usually 24–48 hours. CDC replication lag is usually minutes to hours. A 3-day window covers the majority of real-world cases. A 7-day window is conservative. More than that is usually an upstream pipeline problem that the lookback window is masking rather than fixing.</p>

    <h3>Pattern 2: Partition-based delete+insert</h3>

    <p>Instead of merging individual rows, delete the last N date partitions entirely and rebuild them from the source. Better suited for aggregation models where the partition is the natural unit of correctness.</p>

<pre><code><span class="tag">{{</span> config(
    materialized=<span class="string">'incremental'</span>,
    incremental_strategy=<span class="string">'delete+insert'</span>,
    unique_key=<span class="string">'event_date'</span>,
    incremental_predicates=[
        <span class="string">"DBT_INTERNAL_DEST.event_date >= dateadd(day, -7, current_date)"</span>
    ]
) <span class="tag">}}</span>

<span class="keyword">SELECT</span>
    DATE(event_time)        <span class="keyword">AS</span> event_date
    , event_type
    , <span class="keyword">COUNT</span>(*)               <span class="keyword">AS</span> event_count
    , <span class="keyword">COUNT</span>(<span class="keyword">DISTINCT</span> user_id) <span class="keyword">AS</span> unique_users
<span class="keyword">FROM</span> <span class="tag">{{</span> source(<span class="string">'app'</span>, <span class="string">'raw_events'</span>) <span class="tag">}}</span>

<span class="tag">{%</span> <span class="keyword">if</span> is_incremental() <span class="tag">%}</span>
<span class="keyword">WHERE</span> _fivetran_synced &gt;= <span class="keyword">DATEADD</span>(day, -7, <span class="keyword">CURRENT_DATE</span>)
    <span class="keyword">AND</span> DATE(event_time) &gt;= <span class="keyword">DATEADD</span>(day, -7, <span class="keyword">CURRENT_DATE</span>)
<span class="tag">{%</span> <span class="keyword">endif</span> <span class="tag">%}</span>

<span class="keyword">GROUP BY</span> 1, 2</code></pre>

    <p>Every run deletes the last 7 days of aggregated results and rebuilds them from source. Late-arriving events that fall within that 7-day window are automatically incorporated. Records older than 7 days are considered final and not touched.</p>

    <p>The <code>incremental_predicates</code> limits the DELETE statement to the same 7-day window, so the warehouse doesn't scan the full history on every run.</p>

    <p>Both filters in the WHERE clause are required. The <code>_fivetran_synced</code> filter captures recently ingested records; the <code>DATE(event_time)</code> filter ensures the SELECT only produces <code>event_date</code> values that fall within the same window as the DELETE predicate. Without the second filter, a late-arriving record with <code>event_time</code> from 30 days ago would produce an aggregate row for that old partition — but the DELETE step would skip it (outside the 7-day window), leaving a duplicate partition row in the target.</p>

    <p>Important: the partition key (<code>event_date</code>) must be derived from <code>event_time</code>, not from <code>ingested_at</code>. You want to correct the business date of the event, not the date it arrived. An event that happened on Monday arriving on Wednesday should land in Monday's partition — as long as Monday is still within the lookback window.</p>

    <h3>Pattern 3: The explicit watermark</h3>

    <p>For cases where you need precise control over what's been processed and what hasn't. Instead of inferring the watermark from the model's own max timestamp, track it explicitly.</p>

<pre><code><span class="tag">{%</span> <span class="keyword">if</span> is_incremental() <span class="tag">%}</span>

<span class="tag">{%</span> set watermark_query <span class="tag">%}</span>
    <span class="keyword">SELECT DATEADD</span>(day, -3, <span class="keyword">MAX</span>(ingested_at))
    <span class="keyword">FROM</span> <span class="tag">{{</span> this <span class="tag">}}</span>
<span class="tag">{%</span> endset <span class="tag">%}</span>

<span class="tag">{%</span> set watermark = run_query(watermark_query).columns[0].values()[0] <span class="tag">%}</span>

<span class="keyword">WHERE</span> _fivetran_synced &gt;= <span class="string">'{{ watermark }}'</span>

<span class="tag">{%</span> <span class="keyword">endif</span> <span class="tag">%}</span></code></pre>

    <p>This makes the lookback calculation explicit in the query rather than embedded in config. Useful when the lookback window varies by model, or when you want to document the completeness guarantee clearly in the SQL itself.</p>

    <h3>Pattern 4: microbatch (dbt 1.9+)</h3>

    <p>dbt 1.9 introduced a native <code>microbatch</code> incremental strategy that handles late-arriving data declaratively. You define the event time column and the batch size, and dbt manages the windowing, partitioning, and backfill logic automatically.</p>

<pre><code><span class="tag">{{</span> config(
    materialized=<span class="string">'incremental'</span>,
    incremental_strategy=<span class="string">'microbatch'</span>,
    event_time=<span class="string">'event_time'</span>,
    begin=<span class="string">'2024-01-01'</span>,
    batch_size=<span class="string">'day'</span>,
    lookback=3
) <span class="tag">}}</span>

<span class="keyword">SELECT</span>
    event_id
    , user_id
    , event_type
    , event_time
<span class="keyword">FROM</span> <span class="tag">{{</span> source(<span class="string">'app'</span>, <span class="string">'raw_events'</span>) <span class="tag">}}</span></code></pre>

    <p>dbt executes a separate query per batch window (day, hour, etc.) and retries failed batches automatically. The <code>lookback: 3</code> setting reprocesses the last 3 days on every run, incorporating late arrivals. The <code>begin</code> date is required — it tells dbt where to start when building the target table for the first time. No manual <code>is_incremental()</code> filter needed — the framework handles the windowing.</p>

    <p>Microbatch is the direction the dbt ecosystem is moving, and it's worth adopting if you're on 1.9 or later. The caveat: <code>event_time</code> must be reliable end-to-end. If the source sends events with incorrect timestamps, microbatch will partition them into the wrong windows with no way to override. The patterns above give you more control when the timestamp can't be trusted.</p>

    <hr>

    <h2>Monitoring for late arrivals</h2>

    <p>The hardest part of late data is that it's invisible until something downstream breaks. A few monitoring patterns help catch it early.</p>

    <h3>dbt source freshness</h3>

    <p>dbt's built-in source freshness checks verify that new data has been ingested recently. Configure it on the <code>_fivetran_synced</code> or equivalent column in your sources YAML:</p>

<pre><code>sources:
  - name: app
    tables:
      - name: raw_events
        loaded_at_field: _fivetran_synced
        freshness:
          warn_after: {count: 1, period: hour}
          error_after: {count: 6, period: hour}</code></pre>

    <p>Run with <code>dbt source freshness</code> in your pipeline. This catches the case where ingestion has stalled entirely — the most severe form of late data. It doesn't catch the subtler case of events with old <code>event_time</code> values arriving in a fresh batch.</p>

    <h3>Late arrival detection test</h3>

    <p>A custom singular test that checks whether any records are still arriving with timestamps more than N days in the past. Add this as a test in your dbt project:</p>

<pre><code><span class="comment">-- tests/assert_no_events_older_than_5_days.sql</span>
<span class="keyword">SELECT</span>
    DATE(event_time)  <span class="keyword">AS</span> event_date
    , <span class="keyword">COUNT</span>(*)         <span class="keyword">AS</span> late_records
<span class="keyword">FROM</span> <span class="tag">{{</span> ref(<span class="string">'stg_events'</span>) <span class="tag">}}</span>
<span class="keyword">WHERE</span>
    ingested_at &gt;= <span class="keyword">CURRENT_TIMESTAMP</span> - <span class="keyword">INTERVAL</span> <span class="string">'1 hour'</span>
    <span class="keyword">AND</span> event_time &lt; <span class="keyword">CURRENT_DATE</span> - <span class="keyword">INTERVAL</span> <span class="string">'5 days'</span>
<span class="keyword">HAVING COUNT</span>(*) &gt; 0</code></pre>

    <p>This returns rows only when records with event timestamps older than 5 days are still being ingested in the last hour. If it fires, you have a source with a late-arrival window wider than your current lookback buffer. Either extend the lookback or escalate to the source team.</p>

    <h3>Row count reconciliation</h3>

    <p>For sources with a known total (subscription billing systems, CRMs with accessible record counts), periodically compare your warehouse total against the source. Gaps that grow consistently over time indicate systematic late arrivals that the lookback window is not catching.</p>

    <p>This is less automated than a dbt test but more reliable for catching structural completeness gaps. A weekly reconciliation query that compares warehouse counts to the source's own reporting API is worth the 20 minutes it takes to set up.</p>

    <hr>

    <h2>Choosing the right pattern</h2>

    <p>The patterns above are not mutually exclusive, and the right choice depends on the grain of the model, the reliability of the source timestamps, and the lateness SLA your stakeholders are willing to accept.</p>

    <div class="tradeoff-grid">
      <div class="tradeoff-row header">
        <div class="tradeoff-cell">Pattern</div>
        <div class="tradeoff-cell">Handles late data</div>
        <div class="tradeoff-cell">Cost</div>
        <div class="tradeoff-cell">Best for</div>
      </div>
      <div class="tradeoff-row">
        <div class="tradeoff-cell">No buffer (naive watermark)</div>
        <div class="tradeoff-cell">No</div>
        <div class="tradeoff-cell">Lowest</div>
        <div class="tradeoff-cell">Guaranteed-complete sources only</div>
      </div>
      <div class="tradeoff-row">
        <div class="tradeoff-cell">Lookback window + merge</div>
        <div class="tradeoff-cell">Within window</div>
        <div class="tradeoff-cell">Low–medium</div>
        <div class="tradeoff-cell">Row-level event tables</div>
      </div>
      <div class="tradeoff-row">
        <div class="tradeoff-cell">delete+insert by partition</div>
        <div class="tradeoff-cell">Within partition window</div>
        <div class="tradeoff-cell">Medium</div>
        <div class="tradeoff-cell">Aggregations by date grain</div>
      </div>
      <div class="tradeoff-row">
        <div class="tradeoff-cell">microbatch (dbt 1.9+)</div>
        <div class="tradeoff-cell">Declaratively, within lookback</div>
        <div class="tradeoff-cell">Medium</div>
        <div class="tradeoff-cell">dbt 1.9+, reliable event_time</div>
      </div>
      <div class="tradeoff-row">
        <div class="tradeoff-cell">Full refresh</div>
        <div class="tradeoff-cell">All of it</div>
        <div class="tradeoff-cell">Highest</div>
        <div class="tradeoff-cell">Correctness over cost, small tables</div>
      </div>
    </div>

    <p>The most important step is making the lateness SLA explicit. A model that reprocesses 3 days should say so in its <code>schema.yml</code> description. Downstream consumers need to know the completeness guarantee — not because they will read it (they won't), but because it forces you to have the conversation about whether the business can tolerate data that may be up to 3 days incomplete before being corrected.</p>

<pre><code>models:
  - name: fct_daily_events
    description: &gt;
      Daily event counts by type. Rebuilt for the last 7 days on every run
      to incorporate late-arriving mobile events. Data older than 7 days is
      considered final and will not be corrected by subsequent pipeline runs.
      Source late-arrival SLA: 72 hours.
    columns:
      - name: event_date
        description: Calendar date of the event (event_time, not ingested_at).
        tests:
          - not_null
          - unique</code></pre>

    <p>That description is more useful than most schema.yml descriptions in production. It tells you what the model does, what it doesn't do, and where the boundary of "correct" sits.</p>

    <hr>

    <h2>When the window isn't enough</h2>

    <p>If your source has a late-arrival window wider than you can practically accommodate with a lookback buffer, the problem is upstream of dbt. A 30-day late-arrival window means either the source system has a fundamental data delivery problem, or the data team is being asked to correct history that the business process generates continuously.</p>

    <p>In those cases, the answer is usually one of:</p>

    <ul>
      <li>Negotiate an SLA with the source team to reduce the late window (with monitoring to enforce it)</li>
      <li>Move to a full rebuild on a schedule — nightly for the last 30 days, weekly for history — and accept the cost</li>
      <li>Separate the "complete but slow" mart from a "fast but potentially incomplete" mart, and be explicit with stakeholders about which view they're using</li>
    </ul>

    <p>The worst outcome is a model with no documented lateness guarantee, a 3-day lookback that doesn't match the actual source SLA, and stakeholders who don't know they're looking at incomplete data. Make the tradeoff visible and let the business decide what's acceptable. That is a more important conversation than any of the implementation patterns above.</p>

    <div class="takeaways">
      <h2>Takeaways</h2>
      <ul>
        <li><strong>Late-arriving data doesn't fail loudly</strong> — it produces results that look correct and aren't. Silent incorrectness is harder to detect than a failing run.</li>
        <li><strong>Store both <code>event_time</code> and <code>ingested_at</code></strong> — they answer different questions. Use <code>ingested_at</code> for incremental filtering; use <code>event_time</code> for business logic.</li>
        <li><strong>Filtering on <code>ingested_at</code> is more reliable for pipeline completeness</strong> — every record the connector delivered gets processed, regardless of when the underlying event occurred.</li>
        <li><strong>A 3-day lookback window with merge strategy handles most real-world cases</strong> — match the window width to the SLA of your slowest source, not to an arbitrary number.</li>
        <li><strong><code>delete+insert</code> by date partition is cleaner for aggregations</strong> — rebuild the affected date ranges entirely rather than merging individual rows into an aggregate.</li>
        <li><strong>dbt 1.9 microbatch automates the windowing</strong> — worth adopting on recent versions when <code>event_time</code> is reliable end-to-end.</li>
        <li><strong>Document the lateness SLA in <code>schema.yml</code></strong> — downstream consumers need to know the completeness guarantee. Making it explicit forces the business conversation about what's acceptable.</li>
        <li><strong>A lookback window masks a source problem; it doesn't fix it</strong> — if the window needs to be 30 days, escalate to the source team before setting that as the new normal.</li>
      </ul>
    </div>

    <p>Every data platform reaches a point where the source SLAs, pipeline architecture, and business expectations need to be aligned. Late-arriving data is often where that conversation finally surfaces — usually because someone noticed the numbers don't add up. Better to design for it explicitly than to discover it under pressure.</p>
