---
title: Your nightly export is a second copy nobody governs
date: 2026-11-24
published_at: '2026-11-24T11:46:01Z'
slug: snowflake-iceberg-share-without-exports
description: Snowflake's Horizon Catalog lets Spark and DuckDB read an Iceberg table
  in place. When to drop the export, how to scope access, and where governance stops.
tags:
- Snowflake
- data-quality
read_time: 8
status: published
---

Every Snowflake account already runs an Apache Iceberg REST catalog. Nobody had to switch it on, yet plenty of teams still run a nightly job that copies a table to S3 so a Spark cluster or a laptop running DuckDB can read it.

That copy lives outside every grant, masking policy and audit log you built in Snowflake. It is also wrong from the moment the source table changes.

<div class="post-brief">
<ul>
<li>Exported files drift, and your grants never travel with them.</li>
<li>Snowflake now lets other engines read the original table in place.</li>
<li>Policy enforcement has gaps, and they depend on the engine.</li>
</ul>
</div>

<div class="callout callout-info">
<span class="callout-label">the example</span>
<p>Salar Norte is fictional: a lithium producer in Chile's Atacama whose analytics team shares daily equipment telemetry with a partner's Spark team and a geologist who lives in DuckDB. The SQL and config below follow the Snowflake, dbt and DuckDB docs as I read them on 19 November 2026. I haven't run them against a live account, so try them in a sandbox first.</p>
</div>

---

## The export is the problem, not the file format

A nightly export is a photocopy of a ledger for every auditor who asks. Each copy is accurate for about an hour. After that, nobody knows which one is current, and copies don't check who reads them.

At Salar Norte, a task unloads `equipment_daily` to a bucket at 02:00 and the partner's Spark job reads it at 06:00. When the analytics team fixes a unit bug at 10:00, every reader keeps yesterday's numbers, and the only access control is whoever holds the bucket keys.

The alternative is a reading room: one ledger, a librarian checking badges at the door. In Snowflake terms, the ledger is a Snowflake-managed Iceberg table, and the librarian is Horizon Catalog.

<figure>
<picture>
<source media="(max-width: 600px)" srcset="../assets/posts/snowflake-iceberg-share-without-exports/export-vs-catalog-mobile.svg">
<img src="../assets/posts/snowflake-iceberg-share-without-exports/export-vs-catalog.svg" alt="Two panels. On the left, labelled before, a Snowflake table feeds a nightly export job that writes files to a bucket, and Spark and DuckDB each read their own stale copy with no Snowflake grants attached. On the right, labelled after, Spark, Trino and DuckDB connect to Horizon Catalog, which checks the role and hands out short-lived storage credentials before each engine reads the same Iceberg table files, while Snowflake reads those files directly.">
</picture>
<figcaption>Before: every consumer reads a copy that left your access model. After: every outside engine asks the catalog, and the catalog checks the role.</figcaption>
</figure>

---

## What Snowflake gives you now

Iceberg is an open table format: a folder of Parquet files plus metadata that says which files make up the current version, like a book's table of contents. A REST catalog is the front desk that hands out the latest contents page over HTTP.

Horizon Catalog exposes that Iceberg REST API on every account:

```text
https://<org>-<account>.snowflakecomputing.com/polaris/api/catalog
```

The Snowflake docs list Spark, Trino, Flink, Dremio, PyIceberg and DuckDB among the engines that can read through it. Reads and writes are both generally available.

The catch is one word: *Snowflake-managed* Iceberg tables. Native Snowflake tables are not exposed, and neither are Snowflake-managed Iceberg tables you filled by running `COPY INTO` on Parquet files. So you don't share `fct_equipment_telemetry`. You build a purpose-made share table in Iceberg format.

If you use dbt, that's one config line. On dbt 2.0, `table_format = 'iceberg'` without an `external_volume` creates the table on Snowflake-managed storage, so you don't have to configure a bucket:

```sql
-- models/share/share_equipment_daily.sql
{{
    config(
        materialized = 'table'
        , table_format = 'iceberg'
    )
}}

SELECT
    telemetry_date
    , equipment_id
    , site_code
    , AVG(engine_temp_c) AS avg_engine_temp_c
    , SUM(operating_minutes) AS operating_minutes
FROM {{ ref('fct_equipment_telemetry') }}
GROUP BY
    telemetry_date
    , equipment_id
    , site_code
```

That model already does one governance job: it holds only daily aggregates, with no operator IDs or raw sensor rows. Put share models in their own schema, one per audience, so there's one place to grant from.

---

## Scope access with a role, not a bucket key

The badge check is ordinary Snowflake access control. The external engine authenticates as a Snowflake user with a role and sees exactly what that role can `SELECT`.

```sql
CREATE ROLE geo_reader;

GRANT USAGE ON DATABASE salar_norte TO ROLE geo_reader;
GRANT USAGE ON SCHEMA salar_norte.share TO ROLE geo_reader;
GRANT SELECT ON TABLE salar_norte.share.share_equipment_daily TO ROLE geo_reader;

CREATE USER geo_duckdb_svc TYPE = SERVICE DEFAULT_ROLE = geo_reader;
GRANT ROLE geo_reader TO USER geo_duckdb_svc;

ALTER USER geo_duckdb_svc ADD PAT geo_duckdb_pat
    DAYS_TO_EXPIRY = 7
    ROLE_RESTRICTION = 'GEO_READER';
```

A programmatic access token (PAT) is a password-like secret tied to one user and one role, expiring here in a week. Swap it for a short-lived access token:

```bash
curl -s -X POST "https://salarnorte-prod.snowflakecomputing.com/polaris/api/catalog/v1/oauth/tokens" \
    --data-urlencode 'grant_type=client_credentials' \
    --data-urlencode 'scope=session:role:GEO_READER' \
    --data-urlencode "client_secret=${GEO_PAT}"
```

<div class="callout callout-warn">
<span class="callout-label">watch out</span>
<p>By default, a service user can only generate or use a PAT if a network policy applies to it. Horizon Catalog doesn't support network policies set at the user level. Put the service user under an account-level network policy, or relax the requirement with an authentication policy, and decide which on purpose.</p>
</div>

The geologist passes that token to DuckDB through its generic bearer-token option, which doesn't refresh, so she reruns the `curl` when it expires. The "warehouse" you attach is your Snowflake *database*, in capitals if you created it without quotes:

```sql
CREATE SECRET horizon (
    TYPE iceberg
    , TOKEN getenv('HORIZON_TOKEN')
);

ATTACH 'SALAR_NORTE' AS sn (
    TYPE iceberg
    , SECRET horizon
    , URI 'https://salarnorte-prod.snowflakecomputing.com/polaris/api/catalog'
);

SELECT site_code, SUM(operating_minutes) AS minutes
FROM sn.SHARE.SHARE_EQUIPMENT_DAILY
WHERE telemetry_date >= DATE '2026-11-01'
GROUP BY site_code;
```

DuckDB never gets bucket keys. It defaults to *vended credentials*: short-lived storage credentials scoped to one table, like a valet key that opens one car and soon stops working.

<img src="../assets/posts/snowflake-iceberg-share-without-exports/duckdb-attach-session.png" alt="DuckDB terminal session that creates an iceberg secret, attaches SALAR_NORTE through the Horizon catalog URI, and prints operating minutes per site code, marked as illustrative.">

---

## Where governance stops

This is the part the launch posts skim over. Grants follow the table to every engine. Masking and row access policies, bouncers who work inside Snowflake, only follow it to some.

The Snowflake Connector for Spark routes queries through Snowflake. The Scan Plan API, in preview for Enterprise Edition and above, has the catalog build a policy-filtered copy for the engine to read; it needs Iceberg SDK 1.11 or later, and the docs name Spark, Trino and PyIceberg. DuckDB has a server-side scan planning setting, but I found nothing in either project's docs confirming it works with Horizon policies.

<div class="pull-quote">
If you can't prove an engine enforces your masking policy, don't share a table that needs one.
</div>

For any engine you haven't tested end to end, share a table that contains only what that reader may see. The aggregate in `share_equipment_daily` *is* the policy: nothing to enforce, so nothing to bypass.

Even the Scan Plan API has limits. Its filtered copy is deleted after 24 hours, so longer queries can fail; only the latest snapshot is readable; and anyone with direct storage access can read around it. Tables converted from externally managed to Snowflake-managed can't be read with vended credentials at all.

<div class="decision-tree">
<p class="decision-tree-title">Should this export become an Iceberg share?</p>
<div class="decision-step">
  <span class="decision-q">The reader's engine speaks Iceberg REST (Spark, Trino, PyIceberg, DuckDB)</span>
  <span class="decision-a">Build a share table and grant a role. <strong>Drop the export.</strong></span>
</div>
<div class="decision-step">
  <span class="decision-q">The data needs masking or row filtering and the engine is DuckDB</span>
  <span class="decision-a">Share a <strong>pre-filtered table</strong>, or wait until you've tested enforcement yourself</span>
</div>
<div class="decision-step">
  <span class="decision-q">The reader wants a spreadsheet, or a vendor needs a file drop</span>
  <span class="decision-a">Keep the export. <strong>Iceberg won't help</strong> someone who opens CSVs in Excel</span>
</div>
</div>

<img src="../assets/posts/snowflake-iceberg-share-without-exports/governance-follows.png" alt="Grid of what follows the table to Spark, DuckDB and a raw bucket reader: Spark gets every protection, DuckDB gets grants, vended credentials and audit but not documented masking or row access, and the bucket reader gets none.">

---

## What it costs

Per the Snowflake docs, catalog API calls cost 0.5 credits per million as Cloud Services (scheduled to start in the second half of 2026, so assume it's on). External engines reading Snowflake-managed storage are billed per request, plus normal cross-region transfer. The Scan Plan API adds serverless compute and temporary storage.

The export costs a nightly unload, storage for every copy, and hours explaining why the partner's numbers don't match yours. I'd take the API calls, and the audit trail: external reads appear in <code>SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY</code> with <code>event_source = 'horizon_irc'</code>. With a bucket full of files, you couldn't answer who read what.

**Try this at work:** pick one export job and list who reads its output. Build the share table, grant a role, issue a seven-day PAT, and ask one reader to run `SHOW ALL TABLES` from their engine. Leave the export running for two weeks in parallel, then delete it.

<div class="takeaways">
<h2>Takeaways</h2>
<ul>
<li><strong>An export is a copy outside your access model</strong> — it drifts, and no grant or audit log follows it.</li>
<li><strong>Every account already has an Iceberg REST catalog</strong> — Horizon serves Snowflake-managed Iceberg tables to outside engines.</li>
<li><strong>Share a purpose-made table</strong> — native tables aren't exposed, and a narrow model is easier to grant.</li>
<li><strong>Roles replace bucket keys</strong> — a role-restricted, short-lived PAT plus vended credentials.</li>
<li><strong>Policy enforcement depends on the engine</strong> — don't assume DuckDB gets masking or row access policies.</li>
</ul>
</div>

## Sources and version notes

Checked on 19 November 2026. The Scan Plan API is in preview and Horizon catalog billing was scheduled to start in the second half of 2026; check both against the current docs before you rely on them.

- [External engines through Horizon Catalog](https://docs.snowflake.com/en/user-guide/tables-iceberg-access-using-external-query-engine-snowflake-horizon): endpoint, engines, billing.
- [Enforcing policies for external engines](https://docs.snowflake.com/en/user-guide/tables-iceberg-query-using-external-query-engine-snowflake-horizon-enforce-access-policies) and [the Scan Plan API](https://docs.snowflake.com/en/user-guide/tables-iceberg-enforce-access-policies-scan-plan-api).
- [Snowflake storage for Iceberg tables](https://docs.snowflake.com/en/user-guide/tables-iceberg-internal-storage) and [programmatic access tokens](https://docs.snowflake.com/en/user-guide/programmatic-access-tokens).
- [dbt: Snowflake and Apache Iceberg](https://docs.getdbt.com/docs/build/iceberg/adapters/snowflake-iceberg-support).
- DuckDB 2.0: [Iceberg extension](https://duckdb.org/docs/2.0/core_extensions/iceberg/overview), [catalogs](https://duckdb.org/docs/2.0/core_extensions/iceberg/catalogs), [options](https://duckdb.org/docs/2.0/core_extensions/iceberg/iceberg_options).

Which export job in your warehouse would you delete first if your readers could query the source directly?