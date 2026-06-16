---
title: "dbt incremental models: the complete guide"
date: 2026-06-11
published_at: 2026-06-11T10:00:00Z
slug: dbt-incremental-models-complete-guide
description: "How incremental models work, when each strategy applies, and the patterns that only surface after something breaks in production."
tags: [dbt]
read_time: 14
status: published
---

<p>Every incremental model story starts the same way. A team builds a dbt model over an events table. It works fine in development. Three months into production, the table has grown to two hundred million rows, the dbt run takes ninety minutes, and someone's weekly Slack message about dashboard freshness has become a daily one.</p>

    <p>The fix is an incremental model. But incremental models have failure modes that basic materializations don't. Understand the mechanism fully, and they're the most powerful tool in your dbt toolkit. Understand them partially, and they'll produce data that looks correct and isn't — which is a worse outcome than a failing run.</p>

    <hr>

    <h2>Why `table` doesn't scale</h2>

    <p>dbt gives you three core materializations out of the box: <code>view</code>, <code>table</code>, and <code>incremental</code>.</p>

    <p>A <code>view</code> is nearly free to build — it's just a saved query — but runs the full computation every time it's queried. Fine for simple lookups, slow for anything complex.</p>

    <p>A <code>table</code> pre-computes and stores the result. Fast to query, but every <code>dbt run</code> drops the table and rebuilds it from scratch. On a 10-million-row model with three joins, that's fine. On a 500-million-row event stream running hourly, you're paying for a full warehouse scan every sixty minutes.</p>

    <p>An <code>incremental</code> model solves this by behaving like a <code>table</code> on the first run, then only processing and merging new data on subsequent runs. The expensive full rebuild becomes a cheap incremental load. The tradeoff: the model is now stateful, which introduces complexity you need to manage explicitly.</p>

    <hr>

    <h2>The anatomy of an incremental model</h2>

    <p>The simplest incremental model looks like this:</p>

<pre><code><span class="tag">{{</span> config(
    materialized=<span class="string">'incremental'</span>,
    unique_key=<span class="string">'event_id'</span>
) <span class="tag">}}</span>

<span class="keyword">SELECT</span>
    event_id
    , user_id
    , event_type
    , event_time
    , session_id
<span class="keyword">FROM</span> <span class="tag">{{</span> source(<span class="string">'app'</span>, <span class="string">'raw_events'</span>) <span class="tag">}}</span>

<span class="tag">{%</span> <span class="keyword">if</span> is_incremental() <span class="tag">%}</span>
<span class="keyword">WHERE</span> event_time &gt; (<span class="keyword">SELECT MAX</span>(event_time) <span class="keyword">FROM</span> <span class="tag">{{</span> this <span class="tag">}}</span>)
<span class="tag">{%</span> <span class="keyword">endif</span> <span class="tag">%}</span></code></pre>

    <p>Two things do most of the work here.</p>

    <p><strong><code>is_incremental()</code></strong> is a Jinja macro that returns <code>true</code> when two conditions are met: the target table already exists in the warehouse, and you are not running with <code>--full-refresh</code>. On the very first run, the table doesn't exist yet, so <code>is_incremental()</code> returns <code>false</code> and the entire source is processed. On every subsequent run, it returns <code>true</code> and only the filtered subset is processed.</p>

    <p><strong><code>{{ this }}</code></strong> refers to the model's own table in the warehouse. The subquery <code>SELECT MAX(event_time) FROM {{ this }}</code> finds the latest timestamp already loaded — the watermark — and pulls only rows newer than that. This is how dbt knows where the last run left off.</p>

    <p>The strict <code>&gt;</code> here means the exact watermark row won't be reprocessed. In production you'll want <code>&gt;=</code> combined with a lookback window (covered below) so late-arriving events don't fall through the gap.</p>

    <hr>

    <h2>Incremental strategies</h2>

    <p>The <code>incremental_strategy</code> config tells dbt what to do with the new rows once it has them. The strategy you choose determines both the correctness guarantees and the performance characteristics of the model.</p>

    <h3>append</h3>

    <p>The simplest strategy: new rows are inserted and nothing else happens. No deduplication, no updates to existing rows.</p>

<pre><code><span class="tag">{{</span> config(
    materialized=<span class="string">'incremental'</span>,
    incremental_strategy=<span class="string">'append'</span>
) <span class="tag">}}</span></code></pre>

    <p>Appropriate when you can guarantee the source never sends duplicates and records never change after they're written — immutable event logs with a reliable deduplication upstream. If your pipeline ever retries (and eventually it will), you'll get duplicate rows with no warning. <code>append</code> trusts the source completely.</p>

    <h3>merge</h3>

    <p>The default strategy for most warehouses and the right choice for most production incremental models. For each row in the new batch, if a row with the same <code>unique_key</code> already exists in the target table, update it; otherwise insert it. A proper upsert.</p>

<pre><code><span class="tag">{{</span> config(
    materialized=<span class="string">'incremental'</span>,
    incremental_strategy=<span class="string">'merge'</span>,
    unique_key=<span class="string">'event_id'</span>
) <span class="tag">}}</span></code></pre>

    <p>The <code>unique_key</code> can be a list of columns for a composite natural key:</p>

<pre><code><span class="tag">{{</span> config(
    materialized=<span class="string">'incremental'</span>,
    unique_key=[<span class="string">'user_id'</span>, <span class="string">'event_date'</span>, <span class="string">'event_type'</span>]
) <span class="tag">}}</span></code></pre>

    <p>On Snowflake and BigQuery, omitting <code>unique_key</code> with <code>merge</code> is a compile-time error — dbt won't run at all. On older adapters it may silently fall back to <code>append</code>. Either way the result is wrong. Always provide one.</p>

    <h3>delete+insert</h3>

    <p>Deletes all rows matching the <code>unique_key</code> (or the <code>incremental_predicates</code> range) from the target table, then inserts the new batch. No per-row comparison — a clean replacement of the affected segment.</p>

<pre><code><span class="tag">{{</span> config(
    materialized=<span class="string">'incremental'</span>,
    incremental_strategy=<span class="string">'delete+insert'</span>,
    unique_key=<span class="string">'event_date'</span>
) <span class="tag">}}</span>

<span class="keyword">SELECT</span>
    DATE(event_time) <span class="keyword">AS</span> event_date
    , event_type
    , <span class="keyword">COUNT</span>(*) <span class="keyword">AS</span> event_count
    , <span class="keyword">COUNT</span>(<span class="keyword">DISTINCT</span> user_id) <span class="keyword">AS</span> unique_users
<span class="keyword">FROM</span> <span class="tag">{{</span> source(<span class="string">'app'</span>, <span class="string">'raw_events'</span>) <span class="tag">}}</span>

<span class="tag">{%</span> <span class="keyword">if</span> is_incremental() <span class="tag">%}</span>
<span class="keyword">WHERE</span> event_date &gt;= <span class="keyword">DATEADD</span>(day, -3, (<span class="keyword">SELECT MAX</span>(event_date) <span class="keyword">FROM</span> <span class="tag">{{</span> this <span class="tag">}}</span>))
<span class="tag">{%</span> <span class="keyword">endif</span> <span class="tag">%}</span>

<span class="keyword">GROUP BY</span> 1, 2</code></pre>

    <p>Works well for aggregation models where you want to replace entire date partitions rather than merge individual rows. On column stores like Snowflake, deleting a partition's worth of rows and re-inserting can be faster than row-level merging. Note the anchor is <code>MAX(event_date) FROM {{ this }}</code>, not <code>CURRENT_DATE</code> — if the pipeline fails and re-runs a day later, the window stays anchored to the last date in the target, not to today's wall clock.</p>

    <h3>insert_overwrite</h3>

    <p>Replaces entire partitions in a single operation. Native to BigQuery and Spark/Databricks. If you're on Snowflake, <code>delete+insert</code> with a date-level key achieves the same result more portably — use that instead.</p>

    <div class="strategy-grid">
      <div class="strategy-row header">
        <div class="strategy-cell">Strategy</div>
        <div class="strategy-cell">Best for</div>
        <div class="strategy-cell">Requires</div>
      </div>
      <div class="strategy-row">
        <div class="strategy-cell"><code>append</code></div>
        <div class="strategy-cell">Immutable event logs, guaranteed-unique sources</div>
        <div class="strategy-cell">No duplicates at source</div>
      </div>
      <div class="strategy-row">
        <div class="strategy-cell"><code>merge</code></div>
        <div class="strategy-cell">Most production models, mutable records</div>
        <div class="strategy-cell"><code>unique_key</code></div>
      </div>
      <div class="strategy-row">
        <div class="strategy-cell"><code>delete+insert</code></div>
        <div class="strategy-cell">Aggregations by date partition</div>
        <div class="strategy-cell"><code>unique_key</code> at partition grain</div>
      </div>
      <div class="strategy-row">
        <div class="strategy-cell"><code>insert_overwrite</code></div>
        <div class="strategy-cell">BigQuery / Spark partition replacement</div>
        <div class="strategy-cell">Partition column defined</div>
      </div>
    </div>

    <h3>Which strategy should you use?</h3>

    <p>Three questions determine the answer: do source records ever change after creation, is the model row-level or aggregated, and which warehouse are you on?</p>

<div class="tradeoff-grid">
<div class="tradeoff-row header">
<div class="tradeoff-cell">Source records</div>
<div class="tradeoff-cell">Model type</div>
<div class="tradeoff-cell">Warehouse</div>
<div class="tradeoff-cell">Strategy</div>
</div>
<div class="tradeoff-row">
<div class="tradeoff-cell">Immutable — never change after creation, source never resends</div>
<div class="tradeoff-cell">Row-level</div>
<div class="tradeoff-cell">Any</div>
<div class="tradeoff-cell"><code>append</code></div>
</div>
<div class="tradeoff-row">
<div class="tradeoff-cell">Mutable — records update after creation (orders, users, subscriptions), or source may resend</div>
<div class="tradeoff-cell">Row-level</div>
<div class="tradeoff-cell">Any</div>
<div class="tradeoff-cell"><code>merge</code></div>
</div>
<div class="tradeoff-row">
<div class="tradeoff-cell">Either</div>
<div class="tradeoff-cell">Aggregated by date (daily SUM / COUNT)</div>
<div class="tradeoff-cell">Snowflake, Redshift, Postgres</div>
<div class="tradeoff-cell"><code>delete+insert</code></div>
</div>
<div class="tradeoff-row">
<div class="tradeoff-cell">Either</div>
<div class="tradeoff-cell">Aggregated by date (daily SUM / COUNT)</div>
<div class="tradeoff-cell">BigQuery, Spark / Databricks</div>
<div class="tradeoff-cell"><code>insert_overwrite</code></div>
</div>
<div class="tradeoff-row">
<div class="tradeoff-cell">Either</div>
<div class="tradeoff-cell">Any — table is small or full build is fast</div>
<div class="tradeoff-cell">Any</div>
<div class="tradeoff-cell"><code>table</code> — skip incremental entirely</div>
</div>
</div>

    <p>If in doubt between <code>append</code> and <code>merge</code>, use <code>merge</code>. The merge overhead is small, and the protection against re-runs and source retries is not.</p>

    <hr>

    <h2>on_schema_change — the quiet killer</h2>

    <p>You've been running an incremental model in production for two months. You add a new column to the SELECT. The existing table doesn't have that column yet. What happens?</p>

    <p>By default: <code>on_schema_change='ignore'</code>. dbt runs without error, inserts rows, and silently drops the new column on the way in. You won't get an alert. The column appears nowhere. The first sign will be someone asking why a metric you just added is all nulls.</p>

    <p>The four options:</p>

<pre><code><span class="tag">{{</span> config(
    materialized=<span class="string">'incremental'</span>,
    on_schema_change=<span class="string">'fail'</span>          <span class="comment">-- error on any schema difference (safest)</span>
    <span class="comment">-- on_schema_change='ignore'              -- default, silently drops new columns</span>
    <span class="comment">-- on_schema_change='append_new_columns'  -- adds new columns, keeps existing</span>
    <span class="comment">-- on_schema_change='sync_all_columns'    -- adds new and removes deleted columns</span>
) <span class="tag">}}</span></code></pre>

    <p>In production, use <code>fail</code> or <code>append_new_columns</code>. <code>fail</code> forces a deliberate <code>--full-refresh</code> whenever the schema changes — a manual gate that keeps you honest. <code>append_new_columns</code> handles the common case of adding columns without drama, but won't handle renames or type changes.</p>

    <p><code>ignore</code> exists for backwards compatibility, not because it's a sensible default. <code>sync_all_columns</code> will remove columns from the warehouse table if you remove them from your SQL — use with caution in anything accessed by downstream consumers.</p>

    <hr>

    <h2>incremental_predicates — the performance win</h2>

    <p>When dbt executes a <code>merge</code>, it compares each row in the incoming batch against the full target table. On a two-billion-row table, even with an indexed join key, this can scan more data than necessary.</p>

    <p><code>incremental_predicates</code> adds a filter on the <em>target table</em> side of the merge, telling the warehouse to only consider rows in a specific range. Snowflake, BigQuery, and Databricks can then skip entire micro-partitions or partitions entirely.</p>

<pre><code><span class="tag">{{</span> config(
    materialized=<span class="string">'incremental'</span>,
    unique_key=<span class="string">'event_id'</span>,
    incremental_predicates=[
        <span class="string">"DBT_INTERNAL_DEST.event_time >= dateadd(day, -7, current_timestamp)"</span>
    ]
) <span class="tag">}}</span></code></pre>

    <p><code>DBT_INTERNAL_DEST</code> is the alias dbt uses for the existing target table in the generated MERGE statement. The predicate above restricts the merge to only consider rows from the last 7 days on the target side, allowing the warehouse to skip everything older. On a Snowflake table clustered on <code>event_time</code>, this is often a 10–50× cost reduction on the merge operation.</p>

    <p>The window in the predicate should be at least as wide as your lookback window in the <code>is_incremental()</code> filter. If you pull 3 days of source rows but only search 2 days of the target for matches, rows in the gap get inserted as duplicates instead of updated.</p>

    <p>Note that <code>current_timestamp</code> here is intentional — unlike the lookback anchor in your <code>is_incremental()</code> WHERE clause, this predicate is a <em>performance hint to the warehouse about which target partitions to scan</em>, not a data completeness guarantee. A slightly stale value just means the warehouse scans a few extra micro-partitions; it doesn't cause data loss. The anchor that matters for correctness is always the one in your model's WHERE clause.</p>

    <hr>

    <h2>The full-refresh flag</h2>

    <p>Any incremental model can be rebuilt from scratch with:</p>

<pre><code>dbt run --select my_model --full-refresh</code></pre>

    <p>This drops the existing table and rebuilds it entirely, ignoring the <code>is_incremental()</code> filter. Use it when:</p>

    <ul>
      <li>You've changed the model's SELECT significantly and the incremental logic would produce incorrect merged results</li>
      <li>You've changed <code>on_schema_change</code> to <code>fail</code> and the schema drifted</li>
      <li>The incremental state is corrupted or the watermark is wrong</li>
      <li>You're testing the model for the first time and want to verify the full build</li>
    </ul>

    <p>Always test your incremental model with a <code>--full-refresh</code> before trusting it in production. If the full-refresh result doesn't match what you expect, the incremental run won't either — it just fails more subtly.</p>

    <hr>

    <h2>Practical patterns</h2>

    <h3>The lookback window</h3>

    <p>The pattern you should add to nearly every incremental model you write. The naive watermark filter <code>WHERE event_time &gt; MAX(event_time)</code> misses any records that arrive late — events that happened three days ago but only reached your pipeline today. Late-arriving data is common enough that building without a buffer is an optimism you'll pay for.</p>

<pre><code><span class="tag">{%</span> <span class="keyword">if</span> is_incremental() <span class="tag">%}</span>
<span class="keyword">WHERE</span> event_time &gt;= <span class="keyword">DATEADD</span>(day, -3, (<span class="keyword">SELECT MAX</span>(event_time) <span class="keyword">FROM</span> <span class="tag">{{</span> this <span class="tag">}}</span>))
<span class="tag">{%</span> <span class="keyword">endif</span> <span class="tag">%}</span></code></pre>

    <p>This reprocesses the last 3 days on every run. The <code>merge</code> strategy handles deduplication — rows already present are updated in place, genuinely new rows are inserted. You process a bit more data; in return you don't have unexplained gaps that surface during a quarterly review.</p>

    <p>How wide should the window be? Check the SLA of your slowest upstream source. Webhook retries typically have a 24–72 hour window. Batch exports from third-party systems can be 24–48 hours behind. Three days covers the vast majority of cases. A week is a reasonable conservative choice. Longer than that is usually a sign that something upstream needs fixing.</p>

    <p>The companion article on <a href="late-arriving-data-dbt-incremental.html">late-arriving data</a> goes deeper on this — what causes it, why it's dangerous, and the full set of patterns for handling it.</p>

    <h3>Building a surrogate key for deduplication</h3>

    <p>If the source doesn't provide a reliable unique identifier, build one. <code>dbt_utils.generate_surrogate_key</code> hashes a list of columns into a consistent ID:</p>

<pre><code><span class="keyword">SELECT</span>
    <span class="tag">{{</span> dbt_utils.generate_surrogate_key([<span class="string">'user_id'</span>, <span class="string">'event_time'</span>, <span class="string">'event_type'</span>]) <span class="tag">}}</span> <span class="keyword">AS</span> event_id
    , user_id
    , event_type
    , event_time
    , session_id
    , properties
<span class="keyword">FROM</span> <span class="tag">{{</span> source(<span class="string">'app'</span>, <span class="string">'raw_events'</span>) <span class="tag">}}</span></code></pre>

    <p>Use this as the <code>unique_key</code> in the config. The merge strategy will handle deduplication on re-runs. Be careful that the columns you choose actually define uniqueness — two clicks at exactly the same millisecond by the same user on the same event type should be rare, but if it happens you'll lose one row silently.</p>

    <h3>event_time vs ingested_at</h3>

    <p>Most incremental filters use <code>event_time</code> — when the event happened. But there are two timestamps worth storing:</p>

<pre><code><span class="keyword">SELECT</span>
    event_id
    , user_id
    , event_type
    , event_time                              <span class="comment">-- when it happened in the product</span>
    , _fivetran_synced        <span class="keyword">AS</span> ingested_at  <span class="comment">-- when the pipeline received it</span>
<span class="keyword">FROM</span> <span class="tag">{{</span> source(<span class="string">'app'</span>, <span class="string">'raw_events'</span>) <span class="tag">}}</span></code></pre>

    <p>Your incremental filter should use <code>ingested_at</code> if you want to guarantee you process everything the pipeline received since the last run, regardless of when the events happened. Your business logic uses <code>event_time</code> — counting events by the window in which they actually occurred.</p>

    <p>Filtering on <code>ingested_at</code> for the incremental logic and <code>event_time</code> for aggregations is the correct split. Using <code>event_time</code> for both looks simpler and will miss late arrivals.</p>

    <h3>Incremental on a daily aggregation model</h3>

    <p>Incremental models work on aggregated grains too, not just row-level event tables. Here's a daily subscription revenue model that uses <code>delete+insert</code> to rebuild the last seven days on every run:</p>

<pre><code><span class="tag">{{</span> config(
    materialized=<span class="string">'incremental'</span>,
    incremental_strategy=<span class="string">'delete+insert'</span>,
    unique_key=<span class="string">'mrr_date'</span>
) <span class="tag">}}</span>

<span class="keyword">SELECT</span>
    DATE(billing_date) <span class="keyword">AS</span> mrr_date
    , <span class="keyword">SUM</span>(mrr_amount)          <span class="keyword">AS</span> total_mrr
    , <span class="keyword">COUNT</span>(<span class="keyword">DISTINCT</span> account_id) <span class="keyword">AS</span> active_accounts
<span class="keyword">FROM</span> <span class="tag">{{</span> ref(<span class="string">'stg_subscriptions'</span>) <span class="tag">}}</span>
<span class="keyword">WHERE</span> status = <span class="string">'active'</span>

<span class="tag">{%</span> <span class="keyword">if</span> is_incremental() <span class="tag">%}</span>
<span class="keyword">AND</span> billing_date &gt;= <span class="keyword">DATEADD</span>(day, -7, (<span class="keyword">SELECT MAX</span>(mrr_date) <span class="keyword">FROM</span> <span class="tag">{{</span> this <span class="tag">}}</span>))
<span class="tag">{%</span> <span class="keyword">endif</span> <span class="tag">%}</span>

<span class="keyword">GROUP BY</span> 1</code></pre>

    <p>On each run, the last 7 days of partitions are deleted and rebuilt from the staging model. The anchor is <code>MAX(mrr_date)</code> from the target table — not <code>CURRENT_DATE</code>. If the pipeline fails on Monday and re-runs on Tuesday, the window is still "7 days before the last date we successfully loaded," not "7 days before today." This handles late-arriving subscription updates correctly and keeps historical dates stable beyond the window.</p>

    <hr>

    <h2>Common mistakes</h2>

    <ol>
      <li><strong>No lookback window.</strong> The <code>&gt; MAX(event_time)</code> filter misses late-arriving records. Add a buffer of at least 1–3 days in every incremental filter you write.</li>
      <li><strong>Anchoring the lookback window to <code>CURRENT_DATE</code> instead of <code>MAX(target_column)</code>.</strong> <code>DATEADD(day, -3, CURRENT_DATE)</code> shifts the window every day. If a pipeline fails Monday night and re-runs Tuesday morning, Monday's tail data falls outside the new window and is permanently missed. Always anchor to <code>(SELECT MAX(ts_col) FROM {{ this }})</code> — it stays fixed to where you actually left off, regardless of when the re-run happens.</li>
      <li><strong>Using <code>on_schema_change='ignore'</code> in production.</strong> The default silently drops new columns. Switch to <code>fail</code> or <code>append_new_columns</code>. Discovering this after a week of missing data is educational but avoidable.</li>
      <li><strong>No <code>unique_key</code> with merge strategy.</strong> Without one, dbt falls back to append behavior on most adapters and you accumulate duplicates with no error to investigate.</li>
      <li><strong>Not running <code>--full-refresh</code> after structural changes.</strong> If you significantly alter the SELECT, incremental logic will merge new-shape rows into old-shape rows. Run a full rebuild after any meaningful schema or logic change.</li>
      <li><strong>Incremental on small tables.</strong> Tables under a few million rows don't benefit from incrementals. The merge overhead can exceed the savings. Use <code>table</code> materialization and remove the complexity entirely.</li>
      <li><strong>Joining two incremental models together.</strong> If <code>model_a</code> is incremental and joins <code>model_b</code> (also incremental), <code>model_a</code> only processes its own new rows — it won't pick up historical corrections from <code>model_b</code> that changed rows already in <code>model_a</code>. Plan join dependencies carefully or use a wider lookback window.</li>
    </ol>

    <hr>

    <h2>When NOT to use incremental</h2>

    <p>Incremental models are powerful, but they add stateful complexity. There are scenarios where simpler materializations are the better choice.</p>

    <p><strong>Type 2 slowly changing dimensions.</strong> SCD Type 2 requires comparing every current record against incoming data to detect changes and open/close validity periods. That's a full comparison of the current state — not incremental logic. Use <code>dbt snapshot</code> for this, which is designed exactly for it.</p>

    <p><strong>Aggregations that correct history.</strong> If you have a daily MRR model and a late-arriving subscription update changes a value from two weeks ago, an incremental model with a 3-day window won't reach back and fix it. For aggregations where historical correctness matters more than speed, use <code>table</code> materialization and accept the full rebuild cost, or use <code>delete+insert</code> with a wide enough window.</p>

    <p><strong>Small or medium reference tables.</strong> If the full build takes under 30 seconds, incremental adds complexity without meaningful savings. Simplicity is a feature. A model that a new team member can understand in two minutes is worth more than a model that saves three seconds of compute.</p>

    <p><strong>When you're uncertain.</strong> Start with <code>table</code> and optimise later when the cost becomes visible. Starting with incremental and discovering the edge cases in production is a more expensive lesson.</p>

    <div class="takeaways">
      <h2>Takeaways</h2>
      <ul>
        <li><strong>Incremental models are stateful</strong> — they remember where they left off, which makes them powerful and requires you to manage that state deliberately.</li>
        <li><strong>Always set <code>on_schema_change: fail</code> or <code>append_new_columns</code></strong> — the <code>ignore</code> default silently drops new columns. You will not get an error. You will get nulls in production.</li>
        <li><strong>Add a lookback window to every incremental filter</strong> — <code>&gt; MAX(event_time)</code> alone misses late arrivals. Three days is a reasonable default; match it to your source SLA.</li>
        <li><strong>Use <code>merge</code> + <code>unique_key</code> as your production default</strong> — it handles both new inserts and updates correctly, with predictable deduplication behaviour.</li>
        <li><strong><code>incremental_predicates</code> unlocks partition pruning on the target table</strong> — essential for large Snowflake or BigQuery tables where a full merge scan is cost-prohibitive.</li>
        <li><strong>Test with <code>--full-refresh</code> before trusting the incremental path</strong> — if the full build is wrong, the incremental run will be wrong in a way that's harder to notice.</li>
        <li><strong>Start with <code>table</code> and migrate to incremental when the cost appears</strong> — premature incremental optimization adds complexity before you understand the failure modes.</li>
      </ul>
    </div>

    <p>The next layer of complexity is late-arriving data — events that happened days ago and are only now reaching your pipeline. The incremental model structure above handles it partially; the <a href="late-arriving-data-dbt-incremental.html">companion article on late-arriving data</a> covers the full set of patterns and why it matters more than most teams realise.</p>

  </div>
