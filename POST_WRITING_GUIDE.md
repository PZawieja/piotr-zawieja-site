# Post-writing guide for goldlayer.dev

Use this guide whenever drafting or editing a post for the site, regardless of
which LLM or editor is being used. The repository and its current publishing
scripts are the source of truth; this guide is the editorial brief.

## How to use this guide

Before writing:

1. Read this guide and inspect one or two relevant posts in `content/posts/`.
   Use them to understand the site's voice and markup, not as text to copy.
2. Confirm the topic, intended reader, and whether the request is for a draft
   or for publication.
3. Research technical claims against current primary sources and record when
   they were checked.
4. Draft the Markdown source and any useful original visual assets.
5. Build and validate using the repository's existing scripts. Do not hand-edit
   generated article pages, the writing archive, RSS, or generated homepage
   sections.
6. Leave review, publication, and deployment to the user unless they explicitly
   asked to publish.

Reusable prompt:

> Read `POST_WRITING_GUIDE.md` and the most relevant existing posts. Write a
> post about **[topic]** for **[intended reader]**. The reader should leave able
> to **[outcome]**. Verify current technical claims against primary sources and
> include useful diagrams or illustrations where they improve understanding.
> Keep all examples synthetic and confidential information out. Prepare a
> reviewable draft; do not publish, commit, or push unless I explicitly ask.

## Audience and subject

Write for people working in analytics engineering, data engineering, and
analytics: practitioners building reliable data products, and the stakeholders
who depend on them. The site should be where analytics engineers come back to
find answers to real problems at work. Relevant themes include reliable and
self-healing pipelines, alerting, warehouse and AI cost, new warehouse features,
dbt practices and large projects, CI/CD and git, developer setups and tools,
semantic layers, analytics agents, context management, model choice, evaluation
and judges, governance, data team structure, and analytics engineering skills.

Each post should have a clear reader and purpose. Prefer a useful, bounded
question over a broad survey. Explain what the reader can understand, decide,
or do differently after reading.

## Voice and explanation

- Be clear, practical, and conversational while staying technically precise.
- Explain concepts in plain language before relying on specialist terminology;
  define acronyms when they first matter.
- Use concrete examples and everyday metaphors to make difficult ideas easier
  to grasp. Connect the metaphor back to the real system and its limitations.
- Write like a columnist, not a manual. The first one to three sentences are a
  hook that sets the tone: a strong or contrarian statement, a sourced number or
  fact, a behaviour readers recognise, a curiosity, or a problem many people
  feel. The hook states or implies the thesis; no warm-up before the point.
- Right after the hook, add a brief of two or three very short bullets (about
  12 words each) that make the case for reading on: the problem, why it
  matters, what most people get wrong, or what the reader gains. State stakes,
  not answers, and never repeat the takeaways.
- Vary how posts open. Avoid a repeated formula such as "a fictional company
  gives its team a tool, then someone asks a question." Fictional worked
  examples belong in the body, and any "this example is fictional" note stays
  short and out of the first lines. Nothing, including series boxes, goes above
  the hook.
- Sound like the author's own research and observations: first person for
  opinions, for what was checked or measured, and for things built. Never
  invent personal anecdotes or attribute made-up numbers to experience.
- Avoid prose that reads as machine-written: stock openers ("Here's how", "The
  real question is", "In today's…"), reflexive "it's not X, it's Y" contrasts,
  lists of three everywhere, em-dash chains, uniform paragraph lengths,
  section-ending recaps, and words like "crucial", "robust", "seamless",
  "leverage", "delve".
- Use light humor only when it feels natural. Never let a joke obscure a
  technical point.
- Be confident where evidence supports it and candid about uncertainty,
  trade-offs, and context. Avoid hype, filler, and universal claims such as
  “always best” when the right choice depends on the system.
- Keep the prose original. Do not imitate another author's distinctive phrasing
  or reproduce large passages from source material.

## Length and series

Readers want actionable answers, not long reads. Aim for a 5-8 minute read
(`read_time` as `scripts/check.py` counts it: all body words, code and HTML
included, divided by 200) with one problem and one outcome per post. When a topic needs more than that, split
it into a series of short posts (usually 2-5). Each part should stand on its
own, state its outcome, and link to the previous and next parts. Cut background
the reader does not need to act; never pad to reach a length.

Write so the reader can learn the topic and apply it at work: a memorable worked
example they can reproduce, at least one diagram that shows how the mechanism
works, and a concrete next step to try.

## A useful article shape

Choose a structure that serves the topic; do not force every post into a
template. A strong post will usually include:

1. A specific title that promises a useful answer, not just a topic.
2. An opening situation, question, or failure mode that makes the problem
   tangible.
3. A short explanation of why the problem matters and what the post will cover.
4. The central idea, explained step by step and supported by a worked example.
5. Practical implementation guidance, including assumptions and trade-offs.
6. Failure modes, limits, and how to test or validate the recommendation.
7. Concise takeaways and sources for claims that need evidence.

Use headings that help readers scan. Tables, callouts, code, and custom HTML
blocks should clarify the subject, not decorate it. Prefer one well-developed
example over a list of shallow examples.

## Research and technical accuracy

- Prefer primary sources: official product documentation, specifications,
  standards, and original research. Use reputable secondary sources only when
  they add necessary context.
- Check version-sensitive claims against documentation for the relevant
  product version. Include a “checked on” date for fast-changing topics and
  explain when advice is product- or version-specific.
- Link sources near the claims they support and include a concise sources
  section when the post relies on external facts. A link is evidence to inspect,
  not proof that the linked page supports the sentence.
- Separate documented behavior from the author's interpretation or
  recommendation. Qualify claims when evidence is incomplete or products differ.
- Verify code, configuration, commands, calculations, dates, and example output.
  Do not present plausible-looking but untested syntax as production-ready.
- For “best practices,” explain the goal, constraints, and trade-offs instead
  of implying that one setup is right for every team.
- Never invent citations, product capabilities, benchmarks, or industry
  consensus. If a claim cannot be verified, remove it or clearly mark it as an
  opinion or hypothesis.

## Examples and confidentiality

- Use fictional companies, people, datasets, and values unless the user provides
  public material and asks to use it.
- Vary the scenario, industry, geography, and data shape across posts. Do not
  default to Germany, retail sales, or the same example business every time.
  Prefer distinctive but plausible situations that make the concept memorable;
  keep the example technically coherent and do not force whimsy.
- Do not include confidential employer or client details, internal architecture,
  private metrics, or identifiable incidents. Anonymizing a name is not enough
  if the underlying details remain recognizable.
- Label synthetic scenarios as fictional when readers could mistake them for
  real customer evidence.
- State assumptions that affect an example's result. Check that sample data,
  arithmetic, units, and conclusions agree with one another.

## Diagrams and illustrations

Use visuals when they make a concept, system boundary, sequence, comparison, or
trade-off easier to understand. SVG diagrams and original illustrations are
welcome; an image is not required just to fill space.

- Prefer authored SVG for architecture, workflows, comparisons, and diagrams
  with labels. Keep labels accurate, legible at mobile sizes, and consistent
  with the site's visual style.
- Use a `<figure>` with an informative `<figcaption>` for meaningful inline
  visuals. Supply useful alternative text; do not repeat the caption verbatim.
- For a complex diagram, simplify it or provide a mobile-specific SVG rather
  than shrinking dense text until it is unreadable.
- Use strong contrast and the site's established palette. Avoid low-contrast
  labels and white text on bright lime backgrounds.
- Keep post assets together under `assets/posts/<slug>/`. Follow existing
  relative-path conventions in Markdown and frontmatter.
- If an image-generation tool is used, review every detail for factual and
  visual errors. Add text, labels, and data in SVG or HTML rather than relying
  on an image model to render them. Use only assets with clear reuse rights.
- Add a feature image, descriptive alt text, and caption when the post benefits
  from one; follow the current frontmatter conventions.

## Repository and publishing conventions

- Put source posts in `content/posts/` using the existing date-and-slug
  filename convention.
- Follow the frontmatter fields and canonical tags already used by published
  posts. The checker currently accepts these tags: `AI`, `dbt`, `Snowflake`,
  and `data-quality`; use only tags that accurately describe the article.
- Edit the Markdown source and source assets. `scripts/build.py` generates the
  article HTML, archive, RSS feed, and homepage writing section.
- After building, run `scripts/check.py` for the post's slug and, when practical,
  for all published posts. Resolve failures and review warnings rather than
  ignoring them.
- Preview the generated article at desktop and mobile widths. Check diagrams,
  images, alt text, links, metadata, and horizontal overflow.
- Do not change a post to `published`, commit, push, or deploy unless the user
  explicitly requests publication. When publication is requested, validate the
  generated site and follow the repository's existing deployment workflow.
- Keep changes focused on the post and its directly related assets. Do not
  modify unrelated site content or generated files by hand.
