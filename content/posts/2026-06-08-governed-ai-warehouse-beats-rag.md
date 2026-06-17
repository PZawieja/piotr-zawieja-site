---
title: "Why governed AI on your warehouse beats RAG on your docs"
date: 2026-06-08
published_at: 2026-06-08T09:00:00Z
slug: governed-ai-warehouse-beats-rag
description: "Most enterprise data AI projects start by indexing documentation — here is why that is backwards, and what a warehouse-native approach looks like instead."
tags: [AI, dbt]
read_time: 10
status: published
---

<p>Most enterprise AI projects for data start the same way: someone exports Confluence, dumps in a few Notion wikis, maybe pulls in some Slack threads, and calls it a knowledge base. Run a retrieval pipeline over it, hook up an LLM, and now the business can "ask questions about data." The demo works. Then three people use it in production and the answers are wrong.</p>

    <p>This is not a model quality problem. It is a source-of-truth problem. And it points to a different architecture entirely.</p>

    <h2>The RAG approach and why it fails</h2>

    <p>The retrieval-augmented generation pattern is straightforward enough. You chunk your documentation, embed it, store the vectors, and at query time you retrieve the most relevant chunks and let the LLM synthesise an answer. For support tickets, product documentation, and legal FAQs, this works reasonably well.</p>

    <p>For business data questions, it has a structural flaw: documentation describes what was planned or what was true at some point. It does not describe what exists in the warehouse right now. Docs get written during a project kickoff, updated once when someone files a complaint, and then drift quietly into irrelevance. The metric definition in your Notion page is probably the version from three strategy pivots ago — Notion pages don't get deprecated, they just quietly become historical fiction.</p>

    <p>A user asks "what is our churn rate this quarter?" The RAG system retrieves a doc that says churn is calculated as cancelled MRR divided by starting MRR, churns out a confident answer, and nobody notices that the definition was revised six months ago to exclude downgrades from the numerator. The warehouse has the correct answer. The wiki does not. You indexed the wiki.</p>

    <p>The real source of truth is the warehouse. The docs are a shadow of it, written by humans, maintained inconsistently, and always lagging.</p>

    <hr>

    <figure style="margin:2rem 0">
      <svg viewBox="0 0 640 300" xmlns="http://www.w3.org/2000/svg" style="width:100%;display:block;border-radius:8px" role="img" aria-label="Architecture comparison: RAG on docs versus governed warehouse approach">
        <title>RAG on docs vs. governed warehouse — architecture comparison</title>

        <!-- Background -->
        <rect width="640" height="300" fill="#141417" rx="8"/>

        <!-- Panel labels -->
        <text x="148" y="24" text-anchor="middle" font-family="'Courier New',Courier,monospace" font-size="9" fill="#9a6060" letter-spacing="2">RAG ON DOCS</text>
        <text x="492" y="24" text-anchor="middle" font-family="'Courier New',Courier,monospace" font-size="9" fill="#c8a96e" letter-spacing="2">GOVERNED WAREHOUSE</text>

        <!-- ── Left column (RAG) ── -->

        <!-- Step 1 -->
        <rect x="30" y="34" width="236" height="38" rx="4" fill="#0d0d0f" stroke="#2a2a2f" stroke-width="1"/>
        <text x="148" y="57" text-anchor="middle" font-family="system-ui,-apple-system,sans-serif" font-size="12" fill="#d4d0c8">User question</text>
        <!-- Arrow -->
        <line x1="148" y1="72" x2="148" y2="81" stroke="#2e2e33" stroke-width="1.5"/>
        <polygon points="144,79 152,79 148,86" fill="#2e2e33"/>

        <!-- Step 2 -->
        <rect x="30" y="86" width="236" height="38" rx="4" fill="#0d0d0f" stroke="#2a2a2f" stroke-width="1"/>
        <text x="148" y="109" text-anchor="middle" font-family="system-ui,-apple-system,sans-serif" font-size="12" fill="#7a7870">Confluence / Notion docs</text>
        <!-- Arrow -->
        <line x1="148" y1="124" x2="148" y2="133" stroke="#2e2e33" stroke-width="1.5"/>
        <polygon points="144,131 152,131 148,138" fill="#2e2e33"/>

        <!-- Step 3 -->
        <rect x="30" y="138" width="236" height="38" rx="4" fill="#0d0d0f" stroke="#2a2a2f" stroke-width="1"/>
        <text x="148" y="161" text-anchor="middle" font-family="system-ui,-apple-system,sans-serif" font-size="12" fill="#7a7870">Embed + vector search</text>
        <!-- Arrow -->
        <line x1="148" y1="176" x2="148" y2="185" stroke="#2e2e33" stroke-width="1.5"/>
        <polygon points="144,183 152,183 148,190" fill="#2e2e33"/>

        <!-- Step 4 -->
        <rect x="30" y="190" width="236" height="38" rx="4" fill="#0d0d0f" stroke="#2a2a2f" stroke-width="1"/>
        <text x="148" y="213" text-anchor="middle" font-family="system-ui,-apple-system,sans-serif" font-size="12" fill="#7a7870">LLM synthesises answer</text>
        <!-- Arrow -->
        <line x1="148" y1="228" x2="148" y2="237" stroke="#2e2e33" stroke-width="1.5"/>
        <polygon points="144,235 152,235 148,242" fill="#2e2e33"/>

        <!-- Result (bad) -->
        <rect x="30" y="242" width="236" height="46" rx="4" fill="#150d0d" stroke="#7a3535" stroke-width="1"/>
        <text x="148" y="261" text-anchor="middle" font-family="system-ui,-apple-system,sans-serif" font-size="11" fill="#c46b6b">Answer from stale docs</text>
        <text x="148" y="278" text-anchor="middle" font-family="system-ui,-apple-system,sans-serif" font-size="10" fill="#5a4040" font-style="italic">definition may be months out of date</text>

        <!-- ── VS divider ── -->
        <line x1="320" y1="16" x2="320" y2="284" stroke="#232328" stroke-width="1" stroke-dasharray="3,4"/>
        <circle cx="320" cy="166" r="16" fill="#141417" stroke="#232328" stroke-width="1"/>
        <text x="320" y="171" text-anchor="middle" font-family="'Courier New',Courier,monospace" font-size="10" fill="#4a4844">vs</text>

        <!-- ── Right column (Governed) ── -->

        <!-- Step 1 -->
        <rect x="374" y="34" width="236" height="38" rx="4" fill="#0d0d0f" stroke="#2a2a2f" stroke-width="1"/>
        <text x="492" y="57" text-anchor="middle" font-family="system-ui,-apple-system,sans-serif" font-size="12" fill="#d4d0c8">User question</text>
        <!-- Arrow -->
        <line x1="492" y1="72" x2="492" y2="81" stroke="#c8a96e" stroke-width="1.5" opacity="0.45"/>
        <polygon points="488,79 496,79 492,86" fill="#c8a96e" opacity="0.45"/>

        <!-- Step 2 -->
        <rect x="374" y="86" width="236" height="38" rx="4" fill="#0d0d0f" stroke="#c8a96e" stroke-width="1" opacity="0.35"/>
        <text x="492" y="104" text-anchor="middle" font-family="system-ui,-apple-system,sans-serif" font-size="12" fill="#c8a96e">LLM: classify intent only</text>
        <text x="492" y="118" text-anchor="middle" font-family="system-ui,-apple-system,sans-serif" font-size="9.5" fill="#7a6a45">no SQL generation</text>
        <!-- Arrow -->
        <line x1="492" y1="124" x2="492" y2="133" stroke="#c8a96e" stroke-width="1.5" opacity="0.45"/>
        <polygon points="488,131 496,131 492,138" fill="#c8a96e" opacity="0.45"/>

        <!-- Step 3 -->
        <rect x="374" y="138" width="236" height="38" rx="4" fill="#0d0d0f" stroke="#c8a96e" stroke-width="1" opacity="0.35"/>
        <text x="492" y="156" text-anchor="middle" font-family="system-ui,-apple-system,sans-serif" font-size="12" fill="#c8a96e">Query template allowlist</text>
        <text x="492" y="170" text-anchor="middle" font-family="system-ui,-apple-system,sans-serif" font-size="9.5" fill="#7a6a45">pre-reviewed · parameterised only</text>
        <!-- Arrow -->
        <line x1="492" y1="176" x2="492" y2="185" stroke="#c8a96e" stroke-width="1.5" opacity="0.45"/>
        <polygon points="488,183 496,183 492,190" fill="#c8a96e" opacity="0.45"/>

        <!-- Step 4 -->
        <rect x="374" y="190" width="236" height="38" rx="4" fill="#0d0d0f" stroke="#c8a96e" stroke-width="1" opacity="0.35"/>
        <text x="492" y="208" text-anchor="middle" font-family="system-ui,-apple-system,sans-serif" font-size="12" fill="#c8a96e">dbt mart (Snowflake)</text>
        <text x="492" y="222" text-anchor="middle" font-family="system-ui,-apple-system,sans-serif" font-size="9.5" fill="#7a6a45">tested · documented · current</text>
        <!-- Arrow -->
        <line x1="492" y1="228" x2="492" y2="237" stroke="#c8a96e" stroke-width="1.5" opacity="0.45"/>
        <polygon points="488,235 496,235 492,242" fill="#c8a96e" opacity="0.45"/>

        <!-- Result (good) -->
        <rect x="374" y="242" width="236" height="46" rx="4" fill="#0c110a" stroke="#c8a96e" stroke-width="1" opacity="0.7"/>
        <text x="492" y="261" text-anchor="middle" font-family="system-ui,-apple-system,sans-serif" font-size="11" fill="#c8a96e">Answer from live warehouse data</text>
        <text x="492" y="278" text-anchor="middle" font-family="system-ui,-apple-system,sans-serif" font-size="10" fill="#5a6a35" font-style="italic">same definition as your dashboards</text>

      </svg>
      <figcaption style="font-family:'JetBrains Mono','Courier New',monospace;font-size:0.7rem;color:#4a4844;text-align:center;margin-top:0.75rem">
        RAG routes through documentation. Governed warehouse routes through tested, live models.
      </figcaption>
    </figure>

    <h2>The alternative: governed AI on structured data</h2>

    <p>Instead of teaching an LLM to synthesise answers from documentation, give it access to a parameterised query layer built on top of your tested, governed dbt models. The architecture is less exciting to describe but far more reliable in practice.</p>

    <p>Think of it like a taxi dispatcher versus a stranger handed a rental car in a city they've never visited. The dispatcher doesn't need to know how to drive every possible route — they just match your request ("airport, please") to a driver who already knows that exact route cold. The rental-car stranger might get you there, might take a detour through a closed bridge, and might confidently turn the wrong way down a one-way street, all while sounding sure of themselves. Free-form SQL generation against a warehouse the model has never truly "driven" is the rental car. Intent classification against a pre-approved template is the dispatcher.</p>

    <p>It works like this: the LLM classifies user intent, matches that intent to an allowlisted query template, fills in the parameters, executes the SQL against the warehouse, and presents the result. At no point does the LLM write SQL. It selects from a finite, reviewed set of templates.</p>

<pre><code><span class="keyword">import</span> re
<span class="keyword">import</span> snowflake.connector

QUERY_TEMPLATES = {
    <span class="string">"monthly_churn_rate"</span>: <span class="string">"""
        SELECT
            DATE_TRUNC('month', churned_at) AS month
            , COUNT(DISTINCT customer_id) AS churned_customers
            , SUM(mrr_lost) AS churned_mrr
            , ROUND(SUM(mrr_lost) / NULLIF(SUM(starting_mrr), 0), 4) AS churn_rate
        FROM mart_subscription_churn
        WHERE DATE_TRUNC('month', churned_at) = DATE_TRUNC('month', '{period}'::DATE)
        GROUP BY 1
    """</span>,
    <span class="string">"new_mrr_by_segment"</span>: <span class="string">"""
        SELECT
            segment
            , SUM(new_mrr) AS new_mrr
            , COUNT(DISTINCT customer_id) AS new_customers
        FROM mart_new_business
        WHERE DATE_TRUNC('month', closed_at) = DATE_TRUNC('month', '{period}'::DATE)
        GROUP BY 1
        ORDER BY 2 DESC
    """</span>,
    <span class="string">"top_churned_accounts"</span>: <span class="string">"""
        SELECT
            customer_id
            , customer_name
            , mrr_lost
            , churn_reason
        FROM mart_subscription_churn
        WHERE DATE_TRUNC('month', churned_at) = DATE_TRUNC('month', '{period}'::DATE)
        ORDER BY mrr_lost DESC
        LIMIT {limit}
    """</span>,
}

<span class="keyword">def</span> run_intent(intent: str, params: dict, conn) -&gt; list[dict]:
    <span class="keyword">if</span> intent <span class="keyword">not in</span> QUERY_TEMPLATES:
        <span class="keyword">raise</span> ValueError(f<span class="string">"Unknown intent: {intent}"</span>)
    safe_params = {
        k: int(v) <span class="keyword">if</span> k == <span class="string">"limit"</span> <span class="keyword">else</span> str(v)
        <span class="keyword">for</span> k, v <span class="keyword">in</span> params.items()
    }
    sql = QUERY_TEMPLATES[intent].format(**safe_params)
    cursor = conn.cursor(snowflake.connector.DictCursor)
    cursor.execute(sql)
    <span class="keyword">return</span> cursor.fetchall()</code></pre>

    <p>The LLM's job is narrow: given a natural language question, pick the right key from <code>QUERY_TEMPLATES</code> and extract the parameter values. That is a classification and extraction task, which LLMs handle well. Writing correct SQL against a schema the LLM has never seen is not a classification task — it is a code generation task with a high failure rate in edge cases.</p>

    <p>You can implement the intent classification with a simple prompt that lists the available intents and their descriptions, asks the model to return a JSON object with <code>intent</code> and <code>params</code>, and validates the output before anything touches the database.</p>

    <hr>

    <h2>Why dbt makes this work</h2>

    <p>The pattern above is only trustworthy if the underlying models are trustworthy. This is where dbt earns its place in the stack.</p>

    <p>Your mart models are documented and tested. The <code>schema.yml</code> descriptions are precise enough to drive the intent-matching prompt — you do not need a separate wiki for the LLM to understand what each template does. The descriptions live next to the models, which means they get updated when the model gets updated. That is a much smaller gap than keeping a Confluence page in sync.</p>

<pre><code><span class="comment"># schema.yml</span>
models:
  - name: mart_subscription_churn
    description: &gt;
      One row per churned subscription. A subscription is counted as churned
      in the month the cancellation became effective. Downgrades are excluded —
      see mart_subscription_downgrades for those. MRR figures use the final
      contracted amount, not list price.
    columns:
      - name: customer_id
        description: Surrogate key from dim_customers.
        tests:
          - not_null
      - name: mrr_lost
        description: Monthly recurring revenue lost at cancellation, in USD cents.
        tests:
          - not_null
          - dbt_utils.expression_is_true:
              expression: <span class="string">">= 0"</span>
      - name: churn_reason
        description: &gt;
          Categorised exit reason from CRM at close. Values: price, competitor,
          product_gap, budget_freeze, unknown.</code></pre>

    <p>The <code>description</code> field on <code>mart_subscription_churn</code> above is specific enough that an LLM can correctly decide whether to route a "why did we lose revenue last month" question to this model versus <code>mart_subscription_downgrades</code>. That specificity comes from writing good dbt docs — something you should be doing anyway for your analysts.</p>

    <p>dbt tests add a second layer of confidence. If the <code>mrr_lost</code> column starts returning negative values because someone changed the upstream transformation, the test catches it before the LLM surfaces a nonsensical answer to a stakeholder. The governance you built for your analytics engineering practice extends to the AI layer for free.</p>

<pre><code><span class="comment">-- mart_subscription_churn.sql (simplified)</span>
<span class="keyword">WITH</span> source <span class="keyword">AS</span> (
    <span class="keyword">SELECT</span> *
    <span class="keyword">FROM</span> {{ ref(<span class="string">'stg_crm_subscriptions'</span>) }}
    <span class="keyword">WHERE</span> status = <span class="string">'cancelled'</span>
)

, enriched <span class="keyword">AS</span> (
    <span class="keyword">SELECT</span>
        s.subscription_id
        , s.customer_id
        , c.customer_name
        , c.segment
        , s.cancelled_at <span class="keyword">AS</span> churned_at
        , s.mrr <span class="keyword">AS</span> mrr_lost
        , s.cancellation_reason <span class="keyword">AS</span> churn_reason
        , b.mrr <span class="keyword">AS</span> starting_mrr
    <span class="keyword">FROM</span> source s
    <span class="keyword">LEFT JOIN</span> {{ ref(<span class="string">'dim_customers'</span>) }} c <span class="keyword">USING</span> (customer_id)
    <span class="keyword">LEFT JOIN</span> {{ ref(<span class="string">'mart_subscription_bookings'</span>) }} b
        <span class="keyword">ON</span> s.customer_id = b.customer_id
        <span class="keyword">AND</span> DATE_TRUNC(<span class="string">'month'</span>, s.cancelled_at)
            = DATE_TRUNC(<span class="string">'month'</span>, b.created_at)
)

<span class="keyword">SELECT</span> * <span class="keyword">FROM</span> enriched</code></pre>

    <hr>

    <h2>What it does not solve</h2>

    <p>This pattern has a hard boundary: it can only answer questions you have templates for. Ask something outside the template library and you get nothing useful. That is not a bug — it is the point. A system that answers every question, some of them incorrectly, is harder to trust than a system that answers a defined set of questions correctly. A confidently wrong answer is a worse outcome than "I don't have a template for that" — the second one at least doesn't end up screenshotted into a board deck.</p>

    <p>The template library needs ongoing maintenance. When the business redefines a metric, the template changes. When a new reporting segment is introduced, a new template gets added. This is maintenance work, but it is the same maintenance work you are doing when you update your dbt models. You are not adding a new workflow, you are extending an existing one.</p>

    <p>It does not replace an analyst. What it does is handle the high-volume routine questions — weekly churn, last month's new MRR by segment, top churned accounts — so that analysts spend their time on questions that actually require judgement. The analyst who was running the same Snowflake query every Monday morning for six stakeholders is now available to think about something harder.</p>

    <div class="decision-tree">
    <p class="decision-tree-title">Decision Tree: RAG, governed templates, or neither?</p>
    <div class="decision-step">
    <span class="decision-q">Question is about policy, process, or "how do I..."</span>
    <span class="decision-a">RAG over docs is fine — <strong>documentation</strong> is the actual source of truth here, not the warehouse.</span>
    </div>
    <div class="decision-step">
    <span class="decision-q">Question is about a metric the warehouse already certifies</span>
    <span class="decision-a">Route it through an <strong>allowlisted query template</strong> against a tested dbt mart — never let the LLM write the SQL.</span>
    </div>
    <div class="decision-step">
    <span class="decision-q">Question doesn't match any existing template</span>
    <span class="decision-a">Say so. <strong>Bounded coverage</strong> beats a confident guess against a schema the model has never really driven.</span>
    </div>
    <div class="decision-step">
    <span class="decision-q">A new recurring question shows up often enough to matter</span>
    <span class="decision-a">Add it to the template library — this is dbt-model maintenance, not a new workflow.</span>
    </div>
    <div class="decision-step">
    <span class="decision-q">Your schema.yml descriptions are vague or missing</span>
    <span class="decision-a">Fix those first — they're the same descriptions driving your intent-matching prompts.</span>
    </div>
    </div>

    <div class="takeaways">
      <h2>Takeaways</h2>
      <ul>
        <li><strong>Index the warehouse, not the wiki</strong> — documentation describes intent; the warehouse contains the actual state of your data, including all the definition changes your docs never caught up with.</li>
        <li><strong>Keep the LLM out of SQL generation</strong> — use it for intent classification and parameter extraction, then execute pre-written, reviewed templates. The failure modes are far more predictable.</li>
        <li><strong>dbt schema.yml descriptions are your LLM's knowledge base</strong> — write precise model and column descriptions and they do double duty: they orient your analysts and they drive your intent-matching prompts without a separate maintenance burden.</li>
        <li><strong>Bounded coverage is a feature, not a limitation</strong> — a system that correctly answers 30 well-defined questions is more useful in practice than one that attempts any question and gets 20% of them wrong.</li>
        <li><strong>The governance you already have extends to the AI layer</strong> — dbt tests, freshness checks, and column-level lineage mean your AI answers inherit the same quality gates as your dashboards.</li>
      </ul>
    </div>

    <p>What is one question your business asks on a weekly basis that you could template right now — and what has stopped you from automating it sooner?</p>

  </div>
