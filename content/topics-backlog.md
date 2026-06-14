# Post topic backlog

Topics queued for goldlayer.dev. Remove a topic when its post goes live.

---

1. **The analytics engineer's debugging toolkit** — how to systematically diagnose wrong numbers in production: grain checks, join audits, timezone traps, filter drift — tool-agnostic patterns that work regardless of your stack

2. **Data observability on a budget** — what you actually need to monitor (freshness, volume, schema drift, metric variance) before you spend $50k/year on a platform tool, and how to build it with what you already have

3. **Writing SQL that future-you can maintain** — naming conventions, CTE structure, avoiding clever tricks that break on the next engineer, the specific patterns that make SQL reviews fast

4. **When to build a metrics layer and when not to** — the honest decision framework: team size, BI tool count, definition stability, AI querying ambition — covering Semantic Layer, LookML, Cube, and the homegrown mart alternative

5. **Columnar databases explained for analytics engineers** — why Snowflake, BigQuery, and DuckDB are fast, what micro-partitioning and clustering actually do, and how to write queries that cooperate with the storage format

6. **The data team's Git workflow that actually sticks** — branching strategy for data projects, PR review culture, handling schema migrations in version control, why Gitflow is the wrong model for most data teams

7. **Idempotency in data pipelines: the one property worth obsessing over** — what it means, why most pipelines violate it silently, and the concrete patterns (surrogate keys, upserts, partition replacement) that make pipelines safe to re-run

8. **Building a data contract with your stakeholders — not your tools** — the social and process layer before the technical one: agreeing on metric definitions, change management, who owns what, and what "breaking change" means in a data context

9. **Python in the analytics stack: where it belongs and where it doesn't** — data transformation vs. SQL, when pandas is the right tool, orchestration scripts, ML feature pipelines — a clear division of responsibility

10. **How to onboard a new data source without breaking what you have** — the intake process: profiling, documenting assumptions, staging conventions, testing strategy, stakeholder sign-off — the checklist teams skip and regret

11. **Analytical SQL patterns every data engineer should know cold** — sessionization, cohort retention, period-over-period with gaps, running totals, funnel conversion — the queries that come up in every project

12. **Warehouse cost optimization that actually moves the needle** — what to measure first, the 20% of changes that produce 80% of savings, and why most cost guides miss the real levers (query patterns, not just warehouse size)

13. **Data quality as a product, not a project** — shifting from one-time cleanup sprints to an ongoing quality practice: ownership models, escalation paths, the difference between catching errors and preventing them

14. **The real cost of a data warehouse migration** — what the vendor comparison spreadsheet misses: query rewrites, function incompatibilities, team retraining, stakeholder communication, and the tail risk that kills timelines

15. **Designing for the analyst who will use your data** — working backwards from BI tool query patterns, how to structure marts for Tableau vs. Metabase vs. notebooks, the grain decisions that make or break usability
