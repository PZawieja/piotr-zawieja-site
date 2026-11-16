---
title: 'Agents on your semantic layer, Part 2: Three additions that make it production-safe.'
date: 2026-06-30
published_at: '2026-06-30T08:20:16Z'
slug: semantic-layer-agent-harden
description: Add disambiguation pre-flight, template matching, and three-tier memory
  to your dbt Semantic Layer agent. Part 2 of 2 — the hardening layer.
tags:
- AI
- dbt
read_time: 12
status: published
feature_image: ../assets/posts/semantic-layer-agent-harden/test-results.png
feature_image_alt: Five test questions comparing the naive agent with the hardened agent.
feature_image_caption: A five-question comparison of the naive and hardened agents.
---

<div class="callout callout-info">
<span class="callout-label">series</span>
<p>This is Part 2 of <em>Agents on your semantic layer</em>: <a href="https://goldlayer.dev/writing/agents-on-semantic-layer-101.html">Part 0 — why they fail</a> · <a href="https://goldlayer.dev/writing/semantic-layer-agent-build.html">Part 1: build the foundation</a> · Part 2: harden it (this post)</p>
<p>Companion code: <a href="https://github.com/PZawieja/semantic-layer-agent">github.com/PZawieja/semantic-layer-agent</a></p>
</div>

The Part 1 agent answers questions. Ask it "what's our churn rate?" and it returns a number — confidently, without asking which churn definition to use. That number will be plausible and based on whichever interpretation the model inferred from context. Which may not be what your VP meant.

This post adds three layers that close the gap: a pre-flight disambiguation check that catches ambiguous terms before the LLM ever sees them, a template library for common question patterns that skips the reasoning step entirely, and three-tier memory so the agent stops asking the same clarifying question every session.

---

## The three things that will break you

<div class="tradeoff-grid">
<div class="tradeoff-row header">
  <span class="tradeoff-cell">Problem</span>
  <span class="tradeoff-cell">How it shows up</span>
  <span class="tradeoff-cell">What fixes it</span>
</div>
<div class="tradeoff-row">
  <span class="tradeoff-cell">Ambiguous question</span>
  <span class="tradeoff-cell">"What's our churn?" → wrong definition picked, no warning</span>
  <span class="tradeoff-cell">Disambiguation pre-flight</span>
</div>
<div class="tradeoff-row">
  <span class="tradeoff-cell">Same clarification every session</span>
  <span class="tradeoff-cell">Users stop using the agent after the third time it asks the same question</span>
  <span class="tradeoff-cell">Session + user memory</span>
</div>
<div class="tradeoff-row">
  <span class="tradeoff-cell">Novel question forced to a template</span>
  <span class="tradeoff-cell">Pattern match succeeds; answer is wrong because the pattern was wrong</span>
  <span class="tradeoff-cell">Confidence threshold on template matching</span>
</div>
</div>

All three are fixable before you touch the agent loop. The first two are pure Python — no LLM calls, no latency, no token cost. The third is a constraint on the template matcher you'll write in Step 6.

---

## Step 5 — The disambiguation pre-flight

Think of this as a spell checker for business terms — except instead of checking spelling, it checks whether a term has multiple valid definitions at your company. Before the agent touches any query, it scans the question for known ambiguous terms and fires a clarifying question if it finds one.

```python
DISAMBIGUATION: dict[str, dict] = {
    "churn": {
        "question": (
            "When you say churn — do you mean attribution to the contract end date "
            "or the cancellation notification date? And customer count or MRR?"
        ),
    },
    "revenue": {
        "question": "Do you need MRR, ARR, or recognized revenue?",
    },
    "active": {
        "question": "Active by subscription status, last login, or last payment date?",
    },
}


def check_disambiguation(question: str, resolved: set[str]) -> str | None:
    q = question.lower()
    for term, cfg in DISAMBIGUATION.items():
        if term in q and term not in resolved:
            return cfg["question"]
    return None
```

The `resolved` set tracks which terms have already been clarified this session. Wire it in before the agent loop:

```python
def run_agent(question: str, resolved: set[str] | None = None) -> str:
    resolved = resolved or set()

    clarification = check_disambiguation(question, resolved)
    if clarification:
        return f"Before I pull that number — {clarification}"

    # ... rest of the loop from Part 1
```

When the user answers the clarification question, extract the resolved term, add it to `resolved`, and pass it into the next `run_agent` call. The check runs in microseconds and adds zero latency to unambiguous questions.

<div class="callout callout-tip">
<span class="callout-label">tip</span>
<p>Start with 3–5 terms — the ones your team actually disagrees on. Add more only when a real question slips through without asking. Maintain DISAMBIGUATION like a glossary: if Finance and RevOps don't agree on a definition, the agent shouldn't pick one silently either.</p>
</div>

<div class="callout callout-warn">
<span class="callout-label">watch out</span>
<p>The disambiguation check only catches terms you've explicitly listed. Any ambiguous term you haven't added will still be resolved silently by the model. Check your query log regularly and add anything that appears more than once in the wrong-answer bucket.</p>
</div>

---

## Step 6 — The template library

For questions that match a known pattern, templates skip the LLM reasoning step entirely and go straight to a structured `execute_metric_query` call. Same answer, lower latency, fully deterministic behavior.

Think of templates like macros in a spreadsheet. You write the formula once, parameterize the variable parts, and apply it instantly every time. The LLM's job becomes pattern recognition — "does this question fit a known form?" — rather than reasoning from scratch.

```python
import re
from dataclasses import dataclass
from typing import Callable


@dataclass
class Template:
    name: str
    pattern: str
    build: Callable[[dict], dict]


TEMPLATES: list[Template] = [
    Template(
        name="period_metric",
        pattern=r"what was (?P<metric>.+?) (?:in |for |)(?P<period>last \w+|q[1-4] \d{4}|this \w+)",
        build=lambda m: {
            "metric_name": m["metric"].strip(),
            "dimensions": ["metric_time"],
            "filters": [f"metric_time__quarter = '{m['period'].upper()}'"],
        },
    ),
    Template(
        name="top_n",
        pattern=r"which (?P<dim>\w+) had the (?:highest|best|most) (?P<metric>.+)",
        build=lambda m: {
            "metric_name": m["metric"].strip(),
            "dimensions": [m["dim"]],
            "limit": 10,
        },
    ),
    Template(
        name="yoy",
        pattern=r"(?P<metric>.+?) (?:vs\.?|versus|compared to) (?:same period |)last year",
        build=lambda m: {
            "metric_name": m["metric"].strip(),
            "dimensions": ["metric_time"],
            "filters": [
                "metric_time__year IN (YEAR(CURRENT_DATE), YEAR(CURRENT_DATE) - 1)"
            ],
        },
    ),
]


def match_template(question: str) -> tuple[str | None, dict | None]:
    for tmpl in TEMPLATES:
        if m := re.search(tmpl.pattern, question.lower()):
            return tmpl.name, tmpl.build(m.groupdict())
    return None, None
```

Wire template matching into the agent entry point, after disambiguation:

```python
def run_agent(question: str, resolved: set[str] | None = None) -> str:
    resolved = resolved or set()

    clarification = check_disambiguation(question, resolved)
    if clarification:
        return f"Before I pull that number — {clarification}"

    tmpl_name, tmpl_args = match_template(question)
    if tmpl_name and tmpl_args:
        result = execute_metric_query(**tmpl_args)
        return f"[template: {tmpl_name}]\n{json.dumps(result, indent=2)}"

    # full agent loop for everything else
    ...
```

<div class="callout callout-warn">
<span class="callout-label">watch out</span>
<p>Regex pattern matching is greedy — it will match partial strings and produce wrong variable extractions. Test every template against at least five real questions from your team before deploying. A wrong template applied with confidence is identical to hallucination: correct-looking, wrong result, no error signal.</p>
</div>

---

## Step 7 — Three-tier memory

The disambiguation check asked "contract end or notification date?" Once the user answers, the agent should never ask again this session. And once you know a user's preference, ideally never ask again at all.

Like a colleague who remembers your preferences — a good one keeps notes. Session notes cover today. Longer-term notes cover their working relationship with you. And a shared style guide covers conventions the whole team agreed on. Memory in an analytics agent works the same way.

```python
import json
from pathlib import Path


class SessionMemory:
    def __init__(self, user_id: str):
        self._session: dict[str, str] = {}
        self._path = Path(f".memory/{user_id}.json")
        self._persistent: dict[str, str] = (
            json.loads(self._path.read_text()) if self._path.exists() else {}
        )

    def get(self, key: str) -> str | None:
        return self._session.get(key) or self._persistent.get(key)

    def set(self, key: str, value: str, persist: bool = False) -> None:
        self._session[key] = value
        if persist:
            self._persistent[key] = value
            self._path.parent.mkdir(exist_ok=True)
            self._path.write_text(json.dumps(self._persistent, indent=2))

    def resolved_terms(self) -> set[str]:
        return set(self._session) | set(self._persistent)

    def context_block(self) -> str:
        if not self._persistent:
            return ""
        prefs = "\n".join(f"- {k}: {v}" for k, v in self._persistent.items())
        return f"User preferences (apply unless overridden this session):\n{prefs}"
```

<img src="../assets/posts/semantic-layer-agent-harden/memory-stack.png" alt="Three horizontal stacked layers on dark background: top layer in blue labeled 'Session dict' showing key-value pairs cleared on process exit; middle layer in gold labeled 'User JSON (.memory/user_id.json)' showing persisted preferences across sessions; bottom layer in green labeled 'ORG_DEFINITIONS (system prompt)' showing company-wide agreed definitions always applied">

Three tiers:

<div class="ts-block">
<div class="ts-row">
  <span class="ts-label">session dict</span>
  <span class="ts-desc">In-memory, cleared when the process exits. Free to implement — no storage needed. Use this for all answers within a single conversation.</span>
</div>
<div class="ts-row">
  <span class="ts-label">user JSON</span>
  <span class="ts-desc">One file per user_id under <code>.memory/</code>. Survives restarts. When a user answers a disambiguation question they've answered before, don't ask — apply it.</span>
</div>
<div class="ts-row">
  <span class="ts-label">ORG_DEFINITIONS</span>
  <span class="ts-desc">Company-wide, injected into every session's system prompt. Set by you, not the user. The agreed definitions that override individual preferences.</span>
</div>
</div>

<div class="callout callout-info">
<span class="callout-label">context</span>
<p>The <code>.memory/</code> directory works fine for internal tools and single-tenant deployments. For multi-tenant or larger-scale deployments, replace the file store with a DB table — the <code>get</code>, <code>set</code>, <code>context_block</code> interface stays the same, and nothing else in the agent changes.</p>
</div>

---

## Step 8 — The complete hardened loop

All four additions wired together: disambiguation, template matching, session memory, and proper `clarify_or_decline` handling.

```python
def run_agent(question: str, user_id: str = "default") -> str:
    memory = SessionMemory(user_id)

    # Pre-flight 1: disambiguation
    clarification = check_disambiguation(question, memory.resolved_terms())
    if clarification:
        return f"Before I pull that number — {clarification}"

    # Pre-flight 2: template match
    tmpl_name, tmpl_args = match_template(question)
    if tmpl_name and tmpl_args:
        result = execute_metric_query(**tmpl_args)
        return f"[template: {tmpl_name}]\n{json.dumps(result, indent=2)}"

    # Full agent loop for everything else
    system = f"{SYSTEM}\n\n{memory.context_block()}"
    messages = [{"role": "user", "content": question}]

    while True:
        response = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=4096,
            system=system,
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            return next(b.text for b in response.content if hasattr(b, "text"))

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                if block.name == "clarify_or_decline":
                    cq = block.input.get("clarifying_question")
                    return cq if cq else block.input.get("reason", "I need more context.")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": dispatch(block.name, block.input),
                })
            messages.append({"role": "user", "content": tool_results})
```

<div class="pull-quote">
Pre-flight checks happen before the LLM sees the question. Disambiguation and template matching add zero API latency to any question they handle — which should be most of your high-frequency questions.
</div>

---

## Step 9 — Five tests to run before calling it done

<img src="../assets/posts/semantic-layer-agent-harden/test-results.png" alt="Five-row test table on dark background. Column headers: Test question, Naive agent result (red), Hardened agent result (green). Row 1: 'What is our churn rate?' — red: returns a number silently — green: 'Before I pull that — notification date or contract end? MRR or customer count?'. Row 2: Same churn question, second session — red: asks again — green: applies saved preference, no question. Row 3: 'What was mrr_monthly last quarter?' — red: invents metric name — green: calls list_metrics, maps to real name. Row 4: 'How does MRR compare to last year?' — red: full LLM reasoning, ~3s — green: template match, instant. Row 5: 'What is our customer lifetime value?' — red: guesses a metric name — green: clarify_or_decline: 'I don't have a CLV metric in the Semantic Layer — do you want to compute it from MRR and churn?'">

<div class="decision-tree">
<p class="decision-tree-title">Five tests to run before your first real deployment</p>
<div class="decision-step">
  <span class="decision-q">Ask "What's our churn rate?" cold</span>
  <span class="decision-a">Should fire the disambiguation question — not return a number</span>
</div>
<div class="decision-step">
  <span class="decision-q">Answer the disambiguation, then ask again next session (same user_id)</span>
  <span class="decision-a">Should skip the question and apply the saved preference</span>
</div>
<div class="decision-step">
  <span class="decision-q">Ask for a metric name that doesn't exist in the Semantic Layer</span>
  <span class="decision-a">Should call list_metrics, map to the real name, or use clarify_or_decline</span>
</div>
<div class="decision-step">
  <span class="decision-q">Ask a question that matches a template ("How does MRR compare to last year?")</span>
  <span class="decision-a">Should use the template path — no LLM reasoning, instant response</span>
</div>
<div class="decision-step">
  <span class="decision-q">Ask about something your Semantic Layer doesn't have ("customer lifetime value")</span>
  <span class="decision-a">Should call clarify_or_decline — not guess at a metric or invent one</span>
</div>
</div>

Run all five against your real Semantic Layer before your first user. The first and the last are the ones that cause the most damage in production. The middle three tell you whether the performance optimizations are working.

---

## What you've built

This is the complete setup stack from Part 0 — now implemented:

<div class="ts-block">
<div class="ts-row">
  <span class="ts-label">list_metrics</span>
  <span class="ts-desc">Called at session start. Agent never guesses metric names.</span>
</div>
<div class="ts-row">
  <span class="ts-label">disambiguation</span>
  <span class="ts-desc">Pre-flight check before any LLM call. Catches "churn", "revenue", "active" before the model guesses.</span>
</div>
<div class="ts-row">
  <span class="ts-label">ORG_DEFINITIONS</span>
  <span class="ts-desc">Company-wide agreed definitions in the system prompt. Applied to every session.</span>
</div>
<div class="ts-row">
  <span class="ts-label">template library</span>
  <span class="ts-desc">Common patterns resolved without LLM reasoning. Deterministic, fast, no token cost.</span>
</div>
<div class="ts-row">
  <span class="ts-label">interpretation confirmation</span>
  <span class="ts-desc">System prompt rule: state interpretation before executing. Catches wrong grain and wrong period.</span>
</div>
<div class="ts-row">
  <span class="ts-label">clarify_or_decline</span>
  <span class="ts-desc">Explicit tool with a strong description. Claude uses it instead of guessing.</span>
</div>
<div class="ts-row">
  <span class="ts-label">user memory</span>
  <span class="ts-desc">Session dict + user JSON. Disambiguation answers persist across sessions per user_id.</span>
</div>
</div>

The code for all seven of these is under 200 lines of Python. The hard part was never the code — it was getting your team to agree on what "churn" means at your company. If you did that work before you started building, the rest is plumbing.

What's the first question at your company that this agent would answer wrong? That's where to start the DISAMBIGUATION dict.

<div class="takeaways">
<h2>Takeaways</h2>
<ul>
<li><strong>Pre-flight beats post-flight</strong> — check for ambiguity before touching the LLM, not after. The disambiguation pre-flight is deterministic, adds zero latency to clean questions, and catches the most common failure class before any API cost is incurred.</li>
<li><strong>Templates cover most high-frequency questions</strong> — in most analytics orgs, 80% of daily queries fit fewer than 10 patterns. Template those first. Every question handled by a template is instant, deterministic, and free.</li>
<li><strong>Three tiers of memory, one interface</strong> — session dict, user JSON, org definitions. Build them in that order. The <code>get</code> / <code>set</code> / <code>context_block</code> interface stays the same whether the backing store is a dict or a database.</li>
<li><strong>clarify_or_decline needs a schema, not just instructions</strong> — giving Claude a typed tool with a strong description is more reliable than telling it in the system prompt to ask when uncertain. The tool is what makes it say no rather than guess.</li>
<li><strong>Five tests reveal more than unit tests</strong> — run the five scenarios above against your real Semantic Layer. Mock tests won't catch wrong metric names, ambiguous dimension selections, or the difference between "user says contract end" and "agent assumed notification date".</li>
</ul>
</div>