---
title: "How to build a modern analytics data platform: the decisions nobody documents"
date: 2026-06-08
published_at: 2026-06-08T08:00:00Z
slug: data-platform-decisions
description: "Everyone writes about the tools. Nobody writes about the architectural choices made in the first three months that you cannot change without rebuilding."
tags: [data-platform, analytics-engineering, dbt]
read_time: 11
status: published
---

<p>Most data platform writeups are comparisons. Snowflake vs BigQuery. Fivetran vs Airbyte. dbt vs SQLMesh. These are real choices, but they are not the ones that determine whether the platform succeeds. The hard decisions are architectural and organisational — made in Slack threads and Notion documents that get deleted, under deadline pressure, by people who will leave the company before the consequences arrive.</p>

    <p>This is an attempt to surface seven of them. Not to give you a checklist, but to name the decisions so you can at least make them deliberately.</p>

    <figure style="margin:2rem 0">
      <svg viewBox="0 0 640 422" xmlns="http://www.w3.org/2000/svg" style="width:100%;display:block;border-radius:8px" role="img" aria-label="Modern analytics data platform architecture — layers from sources to consumption">
        <title>Modern analytics data platform — architecture overview</title>

        <!-- Background -->
        <rect width="640" height="422" fill="#141417" rx="8"/>

        <!-- ─── SOURCES ─── -->
        <text x="320" y="32" text-anchor="middle" font-family="'Courier New',Courier,monospace" font-size="9" letter-spacing="2" fill="#4a4844">SOURCES</text>
        <rect x="32"  y="40" width="120" height="30" rx="4" fill="#0d0d0f" stroke="#2a2a2f" stroke-width="1"/>
        <text x="92"  y="59" text-anchor="middle" font-family="system-ui,-apple-system,sans-serif" font-size="11" fill="#7a7870">Salesforce</text>
        <rect x="184" y="40" width="120" height="30" rx="4" fill="#0d0d0f" stroke="#2a2a2f" stroke-width="1"/>
        <text x="244" y="59" text-anchor="middle" font-family="system-ui,-apple-system,sans-serif" font-size="11" fill="#7a7870">Chargebee</text>
        <rect x="336" y="40" width="120" height="30" rx="4" fill="#0d0d0f" stroke="#2a2a2f" stroke-width="1"/>
        <text x="396" y="59" text-anchor="middle" font-family="system-ui,-apple-system,sans-serif" font-size="11" fill="#7a7870">Product DB</text>
        <rect x="488" y="40" width="120" height="30" rx="4" fill="#0d0d0f" stroke="#2a2a2f" stroke-width="1"/>
        <text x="548" y="59" text-anchor="middle" font-family="system-ui,-apple-system,sans-serif" font-size="11" fill="#7a7870">Event stream</text>

        <!-- Arrow → Ingestion -->
        <line x1="320" y1="70" x2="320" y2="82" stroke="#2e2e33" stroke-width="1.5"/>
        <polygon points="316,80 324,80 320,88" fill="#2e2e33"/>

        <!-- ─── INGESTION ─── -->
        <rect x="30" y="88" width="580" height="38" rx="4" fill="#0d0d0f" stroke="#2a2a2f" stroke-width="1"/>
        <text x="320" y="104" text-anchor="middle" font-family="'Courier New',Courier,monospace" font-size="9" letter-spacing="2" fill="#4a4844">INGESTION</text>
        <text x="320" y="118" text-anchor="middle" font-family="system-ui,-apple-system,sans-serif" font-size="11" fill="#5a5a58">Fivetran · Airbyte · custom connectors</text>

        <!-- Arrow → dbt -->
        <line x1="320" y1="126" x2="320" y2="138" stroke="#2e2e33" stroke-width="1.5"/>
        <polygon points="316,136 324,136 320,144" fill="#2e2e33"/>

        <!-- ─── dbt PROJECT container ─── -->
        <rect x="30" y="144" width="580" height="208" rx="6" fill="#0f0f12" stroke="#c8a96e" stroke-width="1" opacity="0.45"/>
        <text x="52" y="160" font-family="'Courier New',Courier,monospace" font-size="9" letter-spacing="2" fill="#c8a96e" opacity="0.6">DBT PROJECT</text>

        <!-- Staging -->
        <rect x="48" y="166" width="544" height="46" rx="4" fill="#141417" stroke="#c8a96e" stroke-width="1" opacity="0.2"/>
        <text x="68" y="184" font-family="'Courier New',Courier,monospace" font-size="9" letter-spacing="1.5" fill="#c8a96e" opacity="0.55">STAGING</text>
        <text x="68" y="200" font-family="system-ui,-apple-system,sans-serif" font-size="10.5" fill="#4a4a48">rename · cast · deduplicate · one model per source table · no business logic</text>

        <!-- Arrow inside -->
        <line x1="320" y1="212" x2="320" y2="222" stroke="#c8a96e" stroke-width="1" opacity="0.2"/>
        <polygon points="316,220 324,220 320,226" fill="#c8a96e" opacity="0.2"/>

        <!-- Intermediate -->
        <rect x="48" y="226" width="544" height="46" rx="4" fill="#141417" stroke="#c8a96e" stroke-width="1" opacity="0.2"/>
        <text x="68" y="244" font-family="'Courier New',Courier,monospace" font-size="9" letter-spacing="1.5" fill="#c8a96e" opacity="0.55">INTERMEDIATE</text>
        <text x="68" y="260" font-family="system-ui,-apple-system,sans-serif" font-size="10.5" fill="#4a4a48">business logic · cross-source joins · not for direct consumption</text>

        <!-- Arrow inside -->
        <line x1="320" y1="272" x2="320" y2="282" stroke="#c8a96e" stroke-width="1" opacity="0.35"/>
        <polygon points="316,280 324,280 320,286" fill="#c8a96e" opacity="0.35"/>

        <!-- Marts -->
        <rect x="48" y="286" width="544" height="46" rx="4" fill="#141417" stroke="#c8a96e" stroke-width="1" opacity="0.55"/>
        <text x="68" y="304" font-family="'Courier New',Courier,monospace" font-size="9" letter-spacing="1.5" fill="#c8a96e">MARTS</text>
        <text x="68" y="320" font-family="system-ui,-apple-system,sans-serif" font-size="10.5" fill="#7a6a45">certified · documented grain · owned · the only layer BI tools and AI agents read</text>

        <!-- Arrow → Consumption -->
        <line x1="320" y1="352" x2="320" y2="364" stroke="#2e2e33" stroke-width="1.5"/>
        <polygon points="316,362 324,362 320,370" fill="#2e2e33"/>

        <!-- ─── CONSUMPTION ─── -->
        <rect x="32"  y="370" width="120" height="30" rx="4" fill="#0d0d0f" stroke="#2a2a2f" stroke-width="1"/>
        <text x="92"  y="389" text-anchor="middle" font-family="system-ui,-apple-system,sans-serif" font-size="11" fill="#7a7870">Tableau</text>
        <rect x="184" y="370" width="120" height="30" rx="4" fill="#0d0d0f" stroke="#2a2a2f" stroke-width="1"/>
        <text x="244" y="389" text-anchor="middle" font-family="system-ui,-apple-system,sans-serif" font-size="11" fill="#7a7870">Power BI</text>
        <rect x="336" y="370" width="120" height="30" rx="4" fill="#0d0d0f" stroke="#2a2a2f" stroke-width="1"/>
        <text x="396" y="389" text-anchor="middle" font-family="system-ui,-apple-system,sans-serif" font-size="11" fill="#7a7870">Streamlit</text>
        <rect x="488" y="370" width="120" height="30" rx="4" fill="#0d0d0f" stroke="#c8a96e" stroke-width="1" opacity="0.55"/>
        <text x="548" y="389" text-anchor="middle" font-family="system-ui,-apple-system,sans-serif" font-size="11" fill="#c8a96e" opacity="0.85">AI / LLM</text>
        <text x="320" y="414" text-anchor="middle" font-family="'Courier New',Courier,monospace" font-size="9" letter-spacing="2" fill="#4a4844">CONSUMPTION</text>

      </svg>
      <figcaption style="font-family:'JetBrains Mono','Courier New',monospace;font-size:0.7rem;color:#4a4844;text-align:center;margin-top:0.75rem">
        The seven decisions live at the transitions between these layers — mostly inside the dbt project boundary.
      </figcaption>
    </figure>

    <h2>Decision 1: Prioritise sources by disagreement, not complexity</h2>

    <p>The instinct is to start with the most technically interesting source — usually the event stream or the product database. They are large, complex, and satisfying to model. They are also invisible to most of the business.</p>

    <p>A better heuristic: start with the source that causes the most disagreement in meetings. In most B2B SaaS companies, that is CRM data (Salesforce) or billing data (Chargebee, Stripe). These sources power the numbers that appear in board decks and sales reviews. The moment you produce reliable, agreed-upon figures from them, you earn organisational credibility. That credibility is the political capital that funds the next six months of work.</p>

    <p>Starting with a complex but low-visibility source produces an excellent pipeline that nobody notices. Build where the pain is. Build where three versions of the same spreadsheet are circulating every Monday morning.</p>

    <hr>

    <h2>Decision 2: Write the layer contract before the first model</h2>

    <p>The staging / intermediate / mart separation is well-documented in dbt's own guides. What is almost never documented is the <em>contract</em> — the explicit, written rules about what each layer may and may not contain.</p>

    <p>Without a written contract, the project drifts. An analyst adds a join to a staging model because it was faster. An engineer puts business logic in a mart because the intermediate model was too far away. Three months later, the same transformation exists in four places with subtly different results, and nobody agrees which one is correct.</p>

    <p>The contract should be short enough to read in two minutes. Put it in your project README:</p>

<pre><code><span class="comment"># Layer contract</span>

Staging      — one model per source table; rename, cast, deduplicate only;
               no joins across sources; no business logic

Intermediate — business logic and cross-source joins;
               never queried directly by BI tools or analysts

Marts        — documented grain, documented owner, documented metric definitions;
               the only layer BI tools and AI agents may read</code></pre>

    <p>Reference it in code review. Enforce it with dbt's <a href="https://docs.getdbt.com/reference/resource-configs/group">model groups</a> or linting rules. The specific rules matter less than the act of writing them down and making them visible.</p>

    <hr>

    <h2>Decision 3: Establish a materialisation policy, not a case-by-case habit</h2>

    <p>Table, view, incremental, or ephemeral — most teams decide on a per-model basis, in the moment, without a policy. That produces an inconsistent project where some marts are views (slow for dashboards), some staging models are tables (burning compute unnecessarily), and incremental models exist wherever someone once had a performance problem.</p>

    <p>A simple default policy eliminates most of the decision overhead:</p>

    <ul>
      <li>Views for staging and lightweight intermediate models — cheap to rebuild, always current</li>
      <li>Tables for marts — fast for BI tools, predictable query performance</li>
      <li>Incremental only when the table is genuinely large <em>and</em> the transformation logic is stable enough to trust without a full rebuild</li>
    </ul>

    <p>The qualifier on incremental is important. An incremental model accumulates errors silently. A logic bug in a full-refresh model gets corrected on the next run. In an incremental model, it affects every row added since the bug was introduced — and you may not notice until someone compares numbers across a date boundary.</p>

    <hr>

    <h2>Decision 4: Who owns the metric definition — and where is that written down</h2>

    <p>This is not a technical decision. It is an organisational one. But it has a technical output: the <code>description</code> field in <code>schema.yml</code>.</p>

    <p>Most B2B SaaS companies have at least two conflicting definitions of MRR. Finance calculates it one way (recognised revenue, adjusted for timing). Sales calculates it another (contracted value, no adjustments). RevOps calculates it a third way (net of upgrades and downgrades, per their own cohort logic). Each team's spreadsheet produces a defensible number. None of them match.</p>

    <p>The platform architect's job is to force this conversation, reach an agreed definition, and record the outcome in the codebase — not in Confluence, not in Notion, but in <code>schema.yml</code> next to the column it describes:</p>

<pre><code><span class="keyword">models</span>:
  - <span class="keyword">name</span>: mart_subscription_mrr
    <span class="keyword">columns</span>:
      - <span class="keyword">name</span>: mrr_usd_cents
        <span class="keyword">description</span>: <span class="string">>
          Monthly recurring revenue at period end, in USD cents. Calculated as
          contracted subscription value divided by contract length in months.
          Excludes usage-based components and one-time fees. Aligns with
          Finance board reporting definition agreed 2025-Q1. For downgrade
          treatment see mart_subscription_downgrades.</span></code></pre>

    <p>The phrase "agreed 2025-Q1" matters. Definitions change. Recording when the definition was agreed prevents the same argument from recurring indefinitely — and makes the next revision a deliberate decision rather than a quiet drift.</p>

    <hr>

    <h2>Decision 5: The documentation standard</h2>

    <p>Four types of documentation serve different readers and different purposes. The decision is where each type lives — and enforcing that consistently.</p>

    <table class="doc-table">
      <thead>
        <tr>
          <th>Type</th>
          <th>Purpose</th>
          <th>Where it lives</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>Column descriptions</td>
          <td>What this field means, how it is calculated, edge cases</td>
          <td><code>schema.yml</code></td>
        </tr>
        <tr>
          <td>Model descriptions</td>
          <td>Grain, owner, what to use this for and what not to</td>
          <td><code>schema.yml</code></td>
        </tr>
        <tr>
          <td>Project context</td>
          <td>Architecture decisions, conventions, domain vocabulary, AI tool configuration</td>
          <td><code>README.md</code> / <code>CLAUDE.md</code></td>
        </tr>
        <tr>
          <td>Change rationale</td>
          <td>Why a definition changed, who approved it, what the previous behaviour was</td>
          <td>dbt model description or commit message</td>
        </tr>
      </tbody>
    </table>

    <p>The failure mode: all of it ends up in Confluence, which falls out of date within weeks because it is decoupled from the code. Documentation that lives adjacent to the code it describes gets updated when the code changes. Documentation in a separate wiki gets updated when someone remembers.</p>

    <p>There is a second-order benefit to <code>schema.yml</code> descriptions specifically: they become the knowledge base for AI querying. If you are building a governed LLM layer on top of your warehouse — as described in <a href="governed-ai-warehouse-beats-rag.html">the governed AI post</a> — the quality of your intent-matching prompts is directly determined by the precision of your model descriptions. Good docs do double duty.</p>

    <hr>

    <h2>Decision 6: Certified versus exploratory models — and making the distinction visible</h2>

    <p>Not all dbt models are equal. Some are certified: reviewed, tested, owned by someone accountable, safe to use in a board presentation. Others are exploratory: built for a specific analysis, not production-maintained, potentially stale after one sprint.</p>

    <p>The distinction must be visible — not just understood by the team who built it, but enforced structurally so that a new analyst connecting a BI tool to the warehouse cannot accidentally land on the wrong model.</p>

    <p>The simplest mechanism is folder structure: <code>marts/certified/</code> and <code>marts/exploratory/</code>. BI tools connect only to <code>marts/certified/</code>. Access policies restrict direct warehouse access to the same boundary. The exploratory folder exists and is usable — it just cannot silently enter a dashboard.</p>

    <p>Without this distinction, an exploratory model will inevitably appear in a board presentation. The number will be wrong in a way that is hard to explain. The person explaining it will blame the data platform. The person who built the exploratory model will have left the company.</p>

    <hr>

    <h2>Decision 7: When to split into multiple dbt projects</h2>

    <p>The most common premature optimisation in data platform design is splitting a dbt project before there is a good reason to do so. Multiple projects add meaningful overhead: separate CI pipelines, cross-project ref management, coordinated deployments, duplicated packages and macros.</p>

    <p>The right trigger is not model count. It is ownership. Two domains need separate projects when they have different teams who need to release independently, who do not want to coordinate deployments, and who have sufficiently different schemas that cross-domain refs would be an exception rather than a norm.</p>

    <p>A practical signal: if your team has never had a deployment conflict between two domains working in the same project, you do not need multiple projects yet. The pain that justifies splitting is real and specific — it arrives when two teams are regularly blocked waiting for each other's releases.</p>

    <p>The intermediate step before splitting is <a href="https://docs.getdbt.com/docs/build/groups">dbt model groups and access policies</a>, available since dbt Core 1.5. These let you enforce ownership and access boundaries within a single project, capturing most of the governance benefit without the operational overhead of separate deployments.</p>

    <hr>

    <h2>The decision that underlies all of them</h2>

    <p>These seven choices look like separate decisions. They are actually one: the decision to treat the analytics layer as a product with an interface contract, not as a collection of queries that happen to live in the same repository.</p>

    <p>A product has documented behaviour. It has owners. It has a distinction between stable interfaces and internal implementation details. It has a process for changing definitions. The <a href="dbt-47-models-nobody-trusts.html">dbt trust problem</a> — multiple models for the same concept, conflicting numbers, dashboards nobody believes — is what happens when analytics is treated as a service request queue instead.</p>

    <p>None of these decisions are technically difficult. The hard part is making them explicitly, writing them down, and enforcing them consistently as the organisation and the model count grow. That is the work that separates a data platform from a data warehouse.</p>

    <div class="takeaways">
      <h2>Seven decisions</h2>
      <ul>
        <li><strong>Prioritise sources by business disagreement</strong> — start where the pain is loudest, not where the data is most interesting.</li>
        <li><strong>Write the layer contract before the first model</strong> — staging, intermediate, mart: what each may and may not contain, in the README.</li>
        <li><strong>Establish a materialisation policy, not a habit</strong> — views for staging, tables for marts, incremental only when the logic is stable.</li>
        <li><strong>Force the metric ownership conversation</strong> — one definition, recorded in schema.yml with the date it was agreed.</li>
        <li><strong>Document adjacent to code, not in a wiki</strong> — schema.yml descriptions stay current; Confluence does not.</li>
        <li><strong>Make certified vs exploratory visible structurally</strong> — folder separation and access policies, not shared understanding.</li>
        <li><strong>Split dbt projects on ownership, not model count</strong> — the trigger is deployment conflict between teams, not a number of models.</li>
      </ul>
    </div>

  </div>
